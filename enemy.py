"""
enemy.py —《英雄大作战 - 原型》敌人角色与波次管理

继承 Entity，补充：
    - 简易有限状态 AI（chase / attack / dodge / idle），每 20 帧重新决策
    - 攻击判定框（get_hitbox）
    - 死亡计时与原地重生 / 波次推进
    - EnemyManager：管理一波敌人、触发下一波

注意：
    - 敌人只通过 player 的公开属性（x/width/facing/hitbox 等）感知玩家，
      不触碰任何 _ 前缀或私有成员
    - AI 决策全部使用帧计数（ai_timer），不依赖 time
"""

import random

import pygame

import settings
import states
from entity import Entity

# ---- 可选依赖：弹道模块（用于检测玩家是否释放弹幕并触发躲避） ----
try:
    import projectile as projectile_module
except Exception:  # pragma: no cover
    projectile_module = None


class Enemy(Entity):
    """敌人角色。"""

    # AI 决策间隔（帧）
    DECISION_INTERVAL = 20
    # 死亡后重生等待帧数（约 2 秒 @60FPS）
    RESPAWN_FRAMES = 120

    # -------------------- 构造 --------------------
    def __init__(self, x, y, wave=0):
        super().__init__(x, y, width=44, height=92)

        # 敌人属性：使用 settings 中的敌人参数
        self.hp_max = settings.ENEMY_HP
        self.hp = settings.ENEMY_HP
        # 敌人不需要 MP/SP 的精细玩法，但基类统一保留
        self.mp_max = 0
        self.mp = 0
        self.sp_max = 0
        self.sp = 0

        # AI 状态
        self.ai_timer = 0
        self.ai_action = "idle"       # chase / attack / dodge / idle
        self.ai_jump_flag = False     # 决策为 "跳跃接近" 时置位，执行后清除
        self.ai_backoff_flag = False  # 决策为 "后退" 时置位

        # 重生计时
        self.respawn_timer = 0

        # 所属波次
        self.wave = wave

        # 参考朝向玩家的快照（决策缓存，避免每帧访问 player）
        self._player_snapshot_x = 0

    # -------------------- 战斗 --------------------
    def get_hitbox(self):
        """
        返回攻击判定框：
            仅在 AttackState 的判定阶段返回
            攻击框位于角色前方，宽 45、高 35
        """
        state = self.state_machine.current
        if not isinstance(state, states.AttackState):
            return None
        if getattr(self, "_phase", None) != "active":
            return None

        width = 45
        height = 35
        if self.facing == 1:
            hx = self.x + self.width
        else:
            hx = self.x - width
        hy = self.y + self.height * 0.28
        return pygame.Rect(int(hx), int(hy), width, height)

    # -------------------- AI 决策 --------------------
    def _decide(self, player):
        """
        每 DECISION_INTERVAL 帧调用一次，根据与玩家的水平距离决定行为。
        所有分支条件已在注释中说明。
        """
        # 计算与玩家的水平距离（用中心点，避免宽度差异带来的偏差）
        dx = player.centerx - self.centerx
        dist = abs(dx)

        # 缓存玩家位置，供执行阶段使用（避免每帧读 player）
        self._player_snapshot_x = player.centerx

        # 朝向玩家
        if dx != 0:
            self.facing = 1 if dx > 0 else -1

        # ---------- 弹道躲避优先：若场上有玩家发出的弹体靠近，尝试闪避 ----------
        if self._should_dodge_projectile(player):
            action = "dodge"
        else:
            roll = random.random()
            if dist > 200:
                # 远距离：几乎必定追击，偶尔 idle 让玩家有机会接近
                action = "chase" if roll < 0.9 else "idle"
            elif dist >= 80:
                # 中距离：50% 追击，30% idle，20% 跳跃接近
                if roll < 0.5:
                    action = "chase"
                elif roll < 0.8:
                    action = "idle"
                else:
                    action = "chase"
                    self.ai_jump_flag = True   # 跳跃接近
            else:
                # 近距离：60% 攻击，20% idle，20% 后退
                if roll < 0.6:
                    action = "attack"
                elif roll < 0.8:
                    action = "idle"
                else:
                    action = "chase"
                    self.ai_backoff_flag = True  # 后退（chase 但方向反向）

        self.ai_action = action

    def _should_dodge_projectile(self, player):
        """
        检测场上是否有朝向自己的玩家弹体，若有则以 ENEMY_DODGE_CHANCE 概率躲避。
        仅通过 projectile 模块的公开列表 PROJECTILES 与弹体公开属性判断。
        """
        if projectile_module is None:
            return False
        projectiles = getattr(projectile_module, "PROJECTILES", None)
        if not projectiles:
            return False

        for p in list(projectiles):
            # 弹体需具备 owner / direction / x 等公开属性
            owner = getattr(p, "owner", None)
            if owner is not player:
                continue
            direction = getattr(p, "direction", 0)
            px = getattr(p, "x", None)
            if px is None:
                continue
            # 弹体朝自己方向飞来（方向与自身相对方向一致）
            toward_self = (px < self.centerx and direction > 0) or (px > self.centerx and direction < 0)
            if toward_self:
                if random.random() < settings.ENEMY_DODGE_CHANCE:
                    return True
        return False

    # -------------------- AI 执行 --------------------
    def _execute_action(self, player):
        """执行当前 AI 行为。"""
        # 只在站立类状态（Idle/Run）时才做主动移动与动作，
        # 攻击/受击/跳跃等非可操作状态不打断。
        current = self.state_machine.current
        can_act = isinstance(current, (states.IdleState, states.RunState))

        # ---------- dodge：跳跃躲避 ----------
        if self.ai_action == "dodge" and can_act:
            if self.on_ground:
                self.state_machine.change_state(states.JumpState)
            self.ai_action = "idle"
            return

        # ---------- attack：进入攻击状态 ----------
        if self.ai_action == "attack" and can_act:
            # 距离仍需在攻击范围内才发起，否则退化为追击
            dist = abs(player.centerx - self.centerx)
            if dist <= settings.ENEMY_ATTACK_RANGE:
                if self.on_ground:
                    self.state_machine.change_state(states.AttackState)
                self.ai_action = "idle"
                return
            else:
                self.ai_action = "chase"

        # ---------- chase：向玩家移动 ----------
        if self.ai_action == "chase" and can_act:
            # 后退标志：方向与朝向相反
            direction = -self.facing if self.ai_backoff_flag else self.facing
            self.vx = direction * settings.ENEMY_SPEED

            # 跳跃接近：站在地面且标记了跳跃
            if self.ai_jump_flag and self.on_ground:
                self.state_machine.change_state(states.JumpState)
                self.ai_jump_flag = False
                self.ai_backoff_flag = False
                return

            self.ai_jump_flag = False
            self.ai_backoff_flag = False
            return

        # ---------- idle：站立不动 ----------
        if self.ai_action == "idle":
            self.vx *= settings.FRICTION
            if abs(self.vx) < 0.1:
                self.vx = 0

    # -------------------- 更新 --------------------
    def update_with_player(self, player):
        """
                更新敌人：
            1. 死亡计时处理
            2. AI 决策 / 执行
            3. hitbox 同步
            4. 父类 update（状态机 / 物理 / 计时器）
        """
        # ---------- 死亡处理 ----------
        if self.dead:
            # 死亡计时由 DeadState 负责推进；这里只递减重生计时
            self.respawn_timer -= 1
            self.hp = 0
            # 交给父类 update：状态机（DeadState）驱动重力与落地，避免重复施加
            super().update()
            return

        # ---------- AI 计时 ----------
        self.ai_timer -= 1
        if self.ai_timer <= 0:
            self.ai_timer = self.DECISION_INTERVAL
            self._decide(player)

        # ---------- 执行当前行为 ----------
        self._execute_action(player)

        # ---------- 父类 update ----------
        super().update()

        # 用自身的 get_hitbox 覆盖状态机生成的默认框
        self.hitbox = self.get_hitbox()

        # 死亡：HP 归零后进入 DeadState 并开始重生计时
        if self.hp <= 0 and not self.dead:
            self._go_dead()

    def _go_dead(self):
        """进入死亡状态并设置重生计时。"""
        self.state_machine.change_state(states.DeadState)
        self.dead = True
        self.dead_timer = 0
        self.respawn_timer = self.RESPAWN_FRAMES
        self.vx = 0
        self.ai_action = "idle"

    def respawn(self):
        """在随机位置重生，HP 回满。"""
        self.x = random.randint(50, settings.WIDTH - 50 - self.width)
        self.y = settings.GROUND_Y - self.height
        self.vx = self.vy = 0
        self.hp = self.hp_max
        self.dead = False
        self.dead_timer = 0
        self.respawn_timer = 0
        self.hitstun_timer = 0
        self.invincible_timer = 0
        self.is_blocking = False
        self.ai_timer = 0
        self.ai_action = "idle"
        self.state_machine.change_state(states.IdleState)

    # -------------------- 绘制 --------------------
    def get_body_color(self):
        return settings.ENEMY_BODY

    def get_dark_color(self):
        return settings.ENEMY_DARK

    def draw(self, surface):
        """绘制敌人：基础人形 + 头顶 HP 条 + 死亡旋转淡出。"""
        if self.dead:
            self._draw_dead_fade(surface)
            return

        super().draw(surface)
        self._draw_hp_bar(surface)

    def _draw_hp_bar(self, surface):
        """
        头顶绘制 HP 条：宽 36、高 4，底槽深灰，填充红色。
        """
        bar_w = 36
        bar_h = 4
        bx = int(self.x + (self.width - bar_w) / 2)
        by = int(self.y - bar_h - 6)

        pygame.draw.rect(surface, settings.DARK_GRAY, (bx, by, bar_w, bar_h))
        ratio = max(0.0, self.hp / self.hp_max if self.hp_max else 0)
        fill_w = int(bar_w * ratio)
        if fill_w > 0:
            pygame.draw.rect(surface, settings.HP_RED, (bx, by, fill_w, bar_h))
        # 描边
        pygame.draw.rect(surface, settings.BLACK, (bx, by, bar_w, bar_h), 1)

    def _draw_dead_fade(self, surface):
        """
        死亡绘制：角色旋转 90 度并逐渐透明。
        用 dead_timer 驱动：0~60 帧内旋转到 90 度、alpha 从 255 降到 60。
        """
        # 创建可旋转带 alpha 的绘制表面（大小取碰撞体对角线）
        size = max(self.width, self.height) + 10
        temp = pygame.Surface((size, size), pygame.SRCALPHA)

        # 在临时表面上画一个简化的倒地人形（压扁矩形 + 头部圆）
        body_w = self.width
        body_h = int(self.height * 0.5)
        ox = (size - body_w) // 2
        oy = (size - body_h) // 2
        body_rect = pygame.Rect(ox, oy, body_w, body_h)
        pygame.draw.rect(temp, settings.ENEMY_BODY, body_rect, border_radius=8)
        pygame.draw.rect(temp, settings.ENEMY_DARK, body_rect, 2, border_radius=8)
        # 头部
        pygame.draw.circle(temp, settings.ENEMY_BODY,
                           (ox + body_w // 2, oy - 4), 10)

        # 旋转角度：0 -> 90 度，随 dead_timer 推进
        progress = min(1.0, self.dead_timer / 60.0)
        angle = -90 * progress * self.facing
        rotated = pygame.transform.rotate(temp, angle)

        # 透明度：255 -> 60
        alpha = int(255 - (255 - 60) * progress)
        rotated.set_alpha(alpha)

        # 以角色底部中心对齐放置
        draw_x = int(self.centerx - rotated.get_width() / 2)
        draw_y = int(self.y + self.height - rotated.get_height())
        surface.blit(rotated, (draw_x, draw_y))


# ============================================================
# 波次管理器
# ============================================================
class EnemyManager:
    """
    管理一波敌人与波次推进：
        - enemies：当前存活的敌人列表
        - current_wave：当前波次索引（0 开始）
        - spawn_wave(n)：按 WAVE_COUNTS 生成第 n 波敌人
        - update(player)：更新所有敌人并清理已完成重生的
        - draw(surface)：绘制全部敌人
        - all_dead()：当前波是否全灭
        - next_wave()：进入下一波
    """

    # 死亡后超过多少帧从列表中彻底移除（等待重生完成后再判断）
    RESPAWN_WINDOW = 120

    def __init__(self, total_waves=None):
        self.enemies = []
        self.current_wave = 0
        self.total_waves = total_waves if total_waves is not None else len(settings.WAVE_COUNTS)
        # 初始化第一波
        self.spawn_wave(self.current_wave)

    # -------------------- 生成波次 --------------------
    def spawn_wave(self, wave_num):
        """
        按 WAVE_COUNTS[wave_num] 生成对应数量的敌人。
        生成位置在 x 方向均匀散开，互不重叠。
        """
        self.enemies = []
        if wave_num >= len(settings.WAVE_COUNTS):
            return
        count = settings.WAVE_COUNTS[wave_num]
        # 敌人从右到左散列生成，避免一出生就堆叠
        spacing = settings.WIDTH // (count + 1)
        for i in range(count):
            ex = settings.WIDTH - spacing * (i + 1)
            ex = max(50, min(settings.WIDTH - 44 - 50, ex))
            enemy = Enemy(ex, settings.GROUND_Y - 92, wave=wave_num)
            self.enemies.append(enemy)

    # -------------------- 更新 --------------------
    def update(self, player):
        """
        更新所有敌人：
            - 调用每个敌人的 update_with_player
            - 已完成重生窗口且死亡超过 RESPAWN_WINDOW 的敌人从列表移除
              （此原型采用“原地重生”，因此通常不会真正移除，
               保留该逻辑以便扩展“一次性敌人”模式）
        """
        for enemy in list(self.enemies):
            enemy.update_with_player(player)

    # -------------------- 绘制 --------------------
    def draw(self, surface):
        """依次绘制所有敌人。"""
        for enemy in self.enemies:
            enemy.draw(surface)

    # -------------------- 波次状态查询 --------------------
    def all_dead(self):
        """
        当前波是否全灭。
        判定标准：所有敌人要么死亡、要么死亡计时已经走完重生窗口。
        本原型为原地重生制，因此当任意敌人处于存活状态即视为未全灭。
        若希望“清光即过波”，请使用 kill_mode。
        """
        if not self.enemies:
            return True
        return all(e.dead for e in self.enemies)

    def alive_count(self):
        """存活敌人数。"""
        return sum(1 for e in self.enemies if not e.dead)

    # -------------------- 波次推进 --------------------
    def next_wave(self):
        """
        进入下一波：
            - current_wave + 1
            - 若已到最后一波则返回 False
            - 否则 spawn_wave 新波次并返回 True
        """
        if self.current_wave + 1 >= self.total_waves:
            return False
        self.current_wave += 1
        self.spawn_wave(self.current_wave)
        return True

    def is_last_wave(self):
        """是否已是最后一波。"""
        return self.current_wave >= self.total_waves - 1