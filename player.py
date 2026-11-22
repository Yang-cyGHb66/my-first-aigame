"""
player.py —《英雄大作战 - 原型》玩家角色

继承 Entity，补充：
    - 输入处理（基于 pygame.key.get_pressed + 上一帧快照实现 just_pressed）
    - 连招逻辑（combo_count / combo_timer）
    - 技能释放（生成能量弹 Projectile）
    - 攻击判定框（get_hitbox，三段攻击框更大）
    - 头顶三属性条、防御盾牌、攻击武器等专属绘制
"""

import pygame

import settings
import states
from entity import Entity

# ---- 可选依赖：容错导入，缺失时静默跳过 ----
try:
    import projectile as projectile_module
except Exception:  # pragma: no cover
    projectile_module = None

try:
    import particle as particle_module
except Exception:  # pragma: no cover
    particle_module = None


class Player(Entity):
    """玩家角色类。"""

    # -------------------- 构造 --------------------
    def __init__(self, x, y):
        super().__init__(x, y, width=48, height=96)

        # ---- 连招相关 ----
        self.combo_count = 0          # 当前连击段数（0-3）
        self.combo_timer = 0          # 连招输入缓冲计时器
        self.combo_display = 0        # 界面显示的连击数
        self.combo_display_timer = 0  # 连击数显示计时器
        # ---- 输入相关 ----
        self.run_held = False         # 是否按住奔跑键
        self.attack_buffer = 0        # 攻击输入缓冲
        # ---- 上一帧按键快照（用于 just_pressed 判定） ----
        self._prev_keys = None
        # ---- 技能冷却，避免一帧内重复触发 ----
        self._skill_cooldown = 0

    # -------------------- just_pressed 辅助 --------------------
    def _just_pressed(self, keys, *keycodes):
        """
        判断本帧是否“刚按下”任一键。
        通过对比上一帧按键快照实现，避免长按重复触发。
        """
        if self._prev_keys is None:
            return False
        for kc in keycodes:
            if keys[kc] and not self._prev_keys[kc]:
                return True
        return False

    def _held(self, keys, *keycodes):
        """判断本帧是否“按住”任一键。"""
        return any(keys[kc] for kc in keycodes)

    # -------------------- 输入处理 --------------------
    def handle_input(self):
        """
        读取键盘输入并写入：
            1. self.input（供状态机读取的快照）
            2. 触发即时动作（跳跃 / 攻击 / 技能 / 防御 / 重开等）
        使用 just_pressed 处理一次性动作，用 held 处理移动与防御。
        """
        keys = pygame.key.get_pressed()
        events = pygame.event.get()

        # ---- 系统级按键：ESC 退出 / R 重开（用事件处理，避免被状态机吞掉） ----
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                elif ev.key == pygame.K_r and self.dead:
                    self.respawn()

        # ---- 方向键 / 奔跑 ----
        left = self._held(keys, pygame.K_a, pygame.K_LEFT)
        right = self._held(keys, pygame.K_d, pygame.K_RIGHT)
        down = self._held(keys, pygame.K_s, pygame.K_DOWN)

        # Shift 作为奔跑修饰键
        shift_held = self._held(keys, pygame.K_LSHIFT, pygame.K_RSHIFT)
        self.run_held = shift_held and (left or right)

        # 设置朝向（有方向输入时更新）
        if left:
            self.facing = -1
        elif right:
            self.facing = 1

        # ---- 跳跃：W/↑ 刚按下 ----
        jump_pressed = self._just_pressed(keys, pygame.K_w, pygame.K_UP)

        # ---- 攻击：J 刚按下 ----
        attack_pressed = self._just_pressed(keys, pygame.K_j)

        # ---- 跳跃攻击：K 刚按下（仅空中有效，交给状态机判定） ----
        air_attack_pressed = self._just_pressed(keys, pygame.K_k)

        # ---- 技能：L 刚按下 ----
        skill_pressed = self._just_pressed(keys, pygame.K_l)

        # ---- 防御：S/↓ 按住 ----
        block_held = down

        # ---- 组装状态机输入快照 ----
        self.set_input({
            "left": left,
            "right": right,
            "jump": jump_pressed,
            "attack": attack_pressed or air_attack_pressed,
            "block": block_held,
            "run": self.run_held,
        })

        # ---- 即时动作：攻击（连招判定） ----
        if attack_pressed and not self.dead:
            self.on_attack_pressed()

        # ---- 即时动作：技能 ----
        if skill_pressed and not self.dead and self._skill_cooldown <= 0:
            if self.release_skill():
                self._skill_cooldown = 15   # 技能最小间隔，防连发

        # 保存本帧按键用于下一帧 just_pressed 对比
        self._prev_keys = keys

    # -------------------- 连招逻辑 --------------------
    def on_attack_pressed(self):
        """
        处理一次攻击按键：
            若仍处于连招窗口内且未达 3 段 -> 段数 +1
            否则重新从第 1 段开始
            设置 combo_timer 缓冲窗口
            切换到 AttackState
        说明：
            combo_timer 是“连段缓冲”窗口，只要在窗口内再次按 J 即可续段。
        """
        if self.combo_timer > 0 and self.combo_count < 3:
            self.combo_count += 1
        else:
            self.combo_count = 1

        self.combo_timer = settings.COMBO_WINDOW

        # 同步显示用连击计数
        self.combo_display = self.combo_count
        self.combo_display_timer = settings.COMBO_WINDOW * 3

        # 切到攻击状态（若已在攻击中，状态机内部会延续连段）
        if not isinstance(self.state_machine.current, states.AttackState):
            self.state_machine.change_state(states.AttackState)

    # -------------------- 技能释放 --------------------
    def release_skill(self):
        """
        释放技能：
            1. 检查 MP 是否足够（>= SKILL_MP_COST）
            2. 消耗 MP
            3. 在身前生成能量弹（速度 12，方向为 facing）
            4. 播放发射粒子特效
        返回：
            True 表示释放成功
        """
        if not self.use_mp(settings.SKILL_MP_COST):
            return False

        # 能量弹生成位置：身前胸口高度
        spawn_x = self.x + (self.width if self.facing == 1 else -30)
        spawn_y = self.y + self.height * 0.35

                # 通过 projectile 模块生成能量弹（缺失时跳过但仍消耗 MP）
        # 注意：必须使用 EnergyBall —— Projectile 基类不接受 direction/speed 参数
        if projectile_module is not None:
            ball_cls = getattr(projectile_module, "EnergyBall", None)
            if ball_cls is not None:
                try:
                    proj = ball_cls(
                        spawn_x, spawn_y,
                        direction=self.facing,
                        speed=12,
                        damage=settings.DMG_SKILL,
                        owner=self,
                    )
                    # 注册：优先加入弹道管理器（统一更新/碰撞/绘制）
                    manager = getattr(self, "projectile_manager", None)
                    if manager is not None and hasattr(manager, "add"):
                        manager.add(proj)
                    else:
                        registry = getattr(projectile_module, "PROJECTILES", None)
                        if isinstance(registry, list):
                            registry.append(proj)
                except Exception:
                    pass

        # 发射粒子特效
        if particle_module is not None:
            try:
                if hasattr(particle_module, "spawn_skill"):
                    particle_module.spawn_skill(spawn_x, spawn_y, self.facing)
                elif hasattr(particle_module, "spawn"):
                    particle_module.spawn(spawn_x, spawn_y)
            except Exception:
                pass

        return True

    # -------------------- 攻击判定框 --------------------
    def get_hitbox(self):
        """
        返回当前攻击判定框：
            - 仅在 AttackState 的判定阶段（_phase == 'active'）返回
            - 攻击框位于角色前方，宽 50、高 40
            - 第三段攻击框更宽（宽 70）
            - 其它时刻返回 None
        """
        state = self.state_machine.current
        if not isinstance(state, states.AttackState):
            return None
        if getattr(self, "_phase", None) != "active":
            return None

        # 第三段带来更大判定框
        width = 70 if self.combo_count >= 3 else 50
        height = 40

        if self.facing == 1:
            hx = self.x + self.width
        else:
            hx = self.x - width
        hy = self.y + self.height * 0.28

        return pygame.Rect(int(hx), int(hy), width, height)

    # -------------------- 更新 --------------------
    def update(self):
        """每帧更新：输入处理 -> 连招计时 -> 父类更新 -> 技能冷却。"""
        # 1. 输入
        self.handle_input()

        # 2. 连招计时器衰减
        if self.combo_timer > 0:
            self.combo_timer -= 1
            if self.combo_timer == 0:
                # 连招窗口结束，重置段数
                self.combo_count = 0

        # 3. 连击数显示计时
        if self.combo_display_timer > 0:
            self.combo_display_timer -= 1
            if self.combo_display_timer == 0:
                self.combo_display = 0

        # 4. 技能冷却
        if self._skill_cooldown > 0:
            self._skill_cooldown -= 1

        # 5. 父类更新（状态机 / 物理 / 恢复 / 计时器）
        super().update()

        # 6. 用 get_hitbox 覆盖状态机生成的默认 hitbox，保证三段更宽等逻辑
        self.hitbox = self.get_hitbox()

    # -------------------- 重生 --------------------
    def respawn(self):
        """死亡后重开：重置属性与状态。"""
        self.hp = self.hp_max
        self.mp = self.mp_max
        self.sp = self.sp_max
        self.vx = self.vy = 0
        self.dead = False
        self.dead_timer = 0
        self.hitstun_timer = 0
        self._hitstun_timer = 0
        self.invincible_timer = 0
        self.combo_count = 0
        self.combo_timer = 0
        self.combo_display = 0
        self.combo_display_timer = 0
        self.state_machine.change_state(states.IdleState)

    # -------------------- 绘制 --------------------
    def get_body_color(self):
        """玩家主体颜色。"""
        return settings.PLAYER_BODY

    def get_dark_color(self):
        """玩家暗部颜色。"""
        return settings.PLAYER_DARK

    def draw(self, surface):
        """绘制玩家：基础人形 + 头顶三属性条 + 防御盾 + 攻击武器。"""
        # 1. 基础人形（父类已处理受击闪烁与死亡压扁）
        super().draw(surface)

        if not self.dead:
            # 2. 头顶三属性条
            self._draw_status_bars(surface)
            # 3. 防御盾
            if self.is_blocking:
                self._draw_shield(surface)
            # 4. 攻击武器（仅判定阶段）
            self._draw_weapon(surface)

        # 5. 连击数浮字（简易显示）
        self._draw_combo(surface)

    def _draw_status_bars(self, surface):
        """
        头顶绘制三个小条：
            HP(红) / MP(蓝) / SP(黄)
            每个宽 30 高 3，自上而下排列。
        """
        bar_w = 30
        bar_h = 3
        gap = 1
        total_h = bar_h * 3 + gap * 2
        bx = int(self.x + (self.width - bar_w) / 2)
        by = int(self.y - total_h - 6)   # 头顶上方 6 像素

        def draw_bar(y, value, max_value, color):
            # 底槽
            pygame.draw.rect(surface, settings.DARK_GRAY, (bx, y, bar_w, bar_h))
            # 填充
            ratio = max(0.0, min(1.0, value / max_value if max_value else 0))
            fill_w = int(bar_w * ratio)
            if fill_w > 0:
                pygame.draw.rect(surface, color, (bx, y, fill_w, bar_h))

        draw_bar(by, self.hp, self.hp_max, settings.HP_RED)
        draw_bar(by + bar_h + gap, self.mp, self.mp_max, settings.MP_BLUE)
        draw_bar(by + (bar_h + gap) * 2, self.sp, self.sp_max, settings.SP_YELLOW)

    def _draw_shield(self, surface):
        """防御时在朝向方向绘制半透明盾牌。"""
        shield_w = 14
        shield_h = int(self.height * 0.7)
        if self.facing == 1:
            sx = int(self.x + self.width - 4)
        else:
            sx = int(self.x - shield_w + 4)
        sy = int(self.y + self.height * 0.15)

        # 用带 alpha 的表面实现半透明
        shield = pygame.Surface((shield_w, shield_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shield, (120, 200, 255, 120), (0, 0, shield_w, shield_h))
        pygame.draw.ellipse(shield, (200, 240, 255, 200), (0, 0, shield_w, shield_h), 2)
        surface.blit(shield, (sx, sy))

    def _draw_weapon(self, surface):
        """攻击判定阶段绘制武器（白色剑形），前摇/后摇显示不同透明度。"""
        state = self.state_machine.current
        if not isinstance(state, states.AttackState):
            return

        phase = getattr(self, "_phase", None)
        if phase not in ("startup", "active", "recovery"):
            return

        # 攻击点：身前肩部高度
        shoulder_x = int(self.x + (self.width + 4 if self.facing == 1 else -4))
        shoulder_y = int(self.y + self.height * 0.32)

        if phase == "active":
            color = settings.WHITE
            length = 70 if self.combo_count >= 3 else 55
        elif phase == "startup":
            color = (200, 200, 200)
            length = 30
        else:  # recovery
            color = (170, 170, 170)
            length = 40

        # 剑形：从肩部向前的一条粗线
        end_x = shoulder_x + self.facing * length
        end_y = shoulder_y - 6
        pygame.draw.line(surface, color, (shoulder_x, shoulder_y), (end_x, end_y), 4)
        # 剑尖弧光
        pygame.draw.circle(surface, color, (end_x, end_y), 3)

    def _draw_combo(self, surface):
        """绘制连击数浮字（简易文本，无需字体文件）。"""
        if self.combo_display <= 1 or self.combo_display_timer <= 0:
            return
        # 用圆点数量近似表示连击数，避免依赖字体
        dots = self.combo_display
        cx = int(self.centerx)
        cy = int(self.y - 20)
        for i in range(dots):
            off = (i - (dots - 1) / 2) * 8
            alpha_color = settings.ORANGE if i < 2 else settings.YELLOW
            pygame.draw.circle(surface, alpha_color, (int(cx + off), cy), 3)