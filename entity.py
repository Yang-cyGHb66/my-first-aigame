"""
entity.py —《英雄大作战 - 原型》游戏实体基类

与 states.py 的约定对齐：
    - 状态机通过 entity.get_input() 获取输入快照
    - 状态机写入 entity.hitbox / on_ground / is_blocking / hp / mp / sp
    - 状态机使用 entity._hitstun_timer 做硬直计时（此处与 hitstun_timer 同步）

依赖：
    - settings.py：全局常量
    - states.py  ：状态机与 IdleState
    - particle   ：粒子特效（可选，缺失时静默跳过）
"""

import math
import pygame

import settings
from states import StateMachine, IdleState

# ---- 可选依赖：粒子模块（不存在时用空实现兜底） ----
try:
    import particle as particle_module
except Exception:  # pragma: no cover - 防御性导入
    particle_module = None


class Entity:
    """
    所有游戏实体（玩家 / 敌人）的基类。
    子类通常只需覆盖 draw() 中的配色与 load() 逻辑。
    """

    # -------------------- 构造 --------------------
    def __init__(self, x, y, width=48, height=96):
        # 位置（左上角坐标）
        self.x = float(x)
        self.y = float(y)
        # 速度
        self.vx = 0.0
        self.vy = 0.0
        # 碰撞体尺寸
        self.width = width
        self.height = height
        # 朝向：1=右，-1=左
        self.facing = 1
        # 三属性
        self.hp_max = settings.HP_MAX
        self.mp_max = settings.MP_MAX
        self.sp_max = settings.SP_MAX
        self.hp = self.hp_max
        self.mp = self.mp_max
        self.sp = self.sp_max
        # 状态
        self.on_ground = False
        self.is_blocking = False
        self.dead = False
        self.dead_timer = 0
        # 计时器
        self.hitstun_timer = 0          # 受击硬直
        self.invincible_timer = 0       # 无敌帧
        # 攻击判定框（由状态机 spawn_hitbox 生成）
        self.hitbox = None
        # 动画帧计数器（驱动腿部摆动等）
        self.anim_frame = 0
        # 状态机：初始为站立
        self.state_machine = StateMachine(self, IdleState)
        # 输入快照（由外部输入系统每帧写入，状态机读取）
        self.input = {}

    # -------------------- 几何属性 --------------------
    @property
    def rect(self):
        """返回碰撞体矩形（整数化，便于碰撞检测）。"""
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)

    @property
    def hurtbox(self):
        """返回受击框：碰撞体向内缩 4 像素。"""
        pad = 4
        return pygame.Rect(
            int(self.x) + pad,
            int(self.y) + pad,
            max(1, self.width - pad * 2),
            max(1, self.height - pad * 2),
        )

    @property
    def centerx(self):
        """水平中心坐标，方便定位。"""
        return self.x + self.width / 2

    @property
    def bottom(self):
        """底部 y 坐标。"""
        return self.y + self.height

    # -------------------- 输入 --------------------
    def get_input(self):
        """供状态机读取的输入快照。"""
        return self.input

    def set_input(self, input_dict):
        """外部输入系统每帧写入输入（left/right/jump/attack/block）。"""
        self.input = input_dict or {}

    # -------------------- 物理 --------------------
    def apply_gravity(self):
        """应用重力；触地后停止垂直速度并置 on_ground=True。"""
        self.vy += settings.GRAVITY
        self.y += self.vy

        # 地面判定：底部越过地面线即落地
        ground_top = settings.GROUND_Y - self.height
        if self.bottom >= settings.GROUND_Y:
            self.y = ground_top
            if self.vy > 0:
                self.vy = 0
            self.on_ground = True
            # 水平速度由地面摩擦处理
        else:
            self.on_ground = False

    def apply_friction(self):
        """在地面上应用摩擦力衰减水平速度。"""
        if self.on_ground:
            self.vx *= settings.FRICTION
            if abs(self.vx) < 0.1:
                self.vx = 0

    def move(self):
        """根据速度移动水平位置，并做简单边界约束。"""
        self.x += self.vx
        # 限制在窗口内
        if self.x < 0:
            self.x = 0
            self.vx = 0
        elif self.x + self.width > settings.WIDTH:
            self.x = settings.WIDTH - self.width
            self.vx = 0

    # -------------------- 战斗 --------------------
    def take_damage(self, amount, attacker=None, knockback=True):
        """
        承受伤害。
            - 无敌帧内直接返回
            - 防御时伤害乘 BLOCK_REDUCTION，且不击退、不进入硬直
            - 否则扣 HP，设置硬直与击退速度
            - 触发粒子与镜头震动
        """
        # 无敌帧保护
        if self.invincible_timer > 0 or self.dead:
            return 0

        actual_damage = amount

        # 防御减伤：不击退，不进入硬直
        if self.is_blocking:
            actual_damage = int(amount * settings.BLOCK_REDUCTION)
            self.hp = max(0, self.hp - actual_damage)
            self._spawn_hit_particles(attacker, blocked=True)
            self._shake_camera(amount * 0.3)
            if self.hp <= 0:
                self._go_dead()
            return actual_damage

        # 正常受击
        self.hp = max(0, self.hp - actual_damage)
        self.hitstun_timer = settings.HITSTUN
        self._hitstun_timer = settings.HITSTUN   # 与状态机字段同步

        # 击退方向：远离攻击者
        if knockback and attacker is not None:
            direction = 1 if self.centerx >= attacker.centerx else -1
            self.vx = direction * settings.KNOCKBACK_X
            self.vy = settings.KNOCKBACK_Y
            self.on_ground = False

        # 特效与镜头
        self._spawn_hit_particles(attacker, blocked=False)
        self._shake_camera(amount)

        # 受击闪烁用硬直计时驱动
        if self.hp <= 0:
            self._go_dead()
        else:
            # 若未处于受击状态，交由外部渲染/状态机切换（此处不强切，避免循环依赖）
            from states import HurtState
            self.state_machine.change_state(HurtState)

        return actual_damage

    def _go_dead(self):
        """切换到死亡状态。"""
        from states import DeadState
        self.vy = settings.KNOCKBACK_Y
        self.state_machine.change_state(DeadState)

    def _spawn_hit_particles(self, attacker, blocked=False):
        """调用粒子模块生成命中特效（模块缺失时静默跳过）。"""
        if particle_module is None:
            return
        try:
            if hasattr(particle_module, "spawn_hit"):
                particle_module.spawn_hit(self.centerx, self.y + self.height / 2, blocked)
            elif hasattr(particle_module, "spawn"):
                particle_module.spawn(self.centerx, self.y + self.height / 2)
        except Exception:
            pass

    def _shake_camera(self, magnitude):
        """触发镜头震动（通过全局 camera 对象，缺失时跳过）。"""
        if particle_module is None:
            return
        camera = getattr(particle_module, "camera", None)
        if camera is not None and hasattr(camera, "shake"):
            try:
                camera.shake(magnitude)
            except Exception:
                pass

    # -------------------- 属性操作 --------------------
    def heal(self, amount):
        """恢复 HP，不超过上限。返回实际恢复量。"""
        before = self.hp
        self.hp = min(self.hp_max, self.hp + amount)
        return self.hp - before

    def use_mp(self, amount):
        """消耗 MP，不足返回 False。"""
        if self.mp < amount:
            return False
        self.mp -= amount
        return True

    def use_sp(self, amount):
        """消耗 SP，不足返回 False。"""
        if self.sp < amount:
            return False
        self.sp -= amount
        return True

    def regen(self):
        """每帧恢复 MP 和 SP（不超过上限）。"""
        self.mp = min(self.mp_max, self.mp + settings.MP_REGEN)
        self.sp = min(self.sp_max, self.sp + settings.SP_REGEN)
        # 保持浮点精度即可，显示时可取整

    # -------------------- 状态机接口 --------------------
    def spawn_hitbox(self):
        """生成攻击判定框（供 AttackState 判定阶段调用）。"""
        attack_w = 40
        attack_h = 30
        if self.facing == 1:
            hx = self.x + self.width
        else:
            hx = self.x - attack_w
        hy = self.y + self.height * 0.3
        self.hitbox = pygame.Rect(int(hx), int(hy), attack_w, attack_h)

    # -------------------- 更新 --------------------
    def update(self):
        """每帧主更新：状态机 -> 物理 -> 属性恢复 -> 计时器。"""
        if self.dead and self.state_machine.current_name != "Dead":
            self._go_dead()

        # 驱动状态机（可能切换状态）
        self.state_machine.update()

        # 硬直计时器同步（状态机使用 _hitstun_timer）
        if self.hitstun_timer > 0:
            self.hitstun_timer -= 1
        if getattr(self, "_hitstun_timer", 0) != self.hitstun_timer:
            # 以双方较大值为准，避免互相覆盖丢失
            self._hitstun_timer = self.hitstun_timer

        # 无敌帧递减
        if self.invincible_timer > 0:
            self.invincible_timer -= 1

        # 物理
        self.move()
        self.apply_gravity()

        # 属性恢复
        self.regen()

        # 动画帧推进
        self.anim_frame += 1

    # -------------------- 绘制 --------------------
    def get_body_color(self):
        """主体绘制颜色（子类可覆盖）。"""
        return settings.PLAYER_BODY

    def get_dark_color(self):
        """暗部描边颜色（子类可覆盖）。"""
        return settings.PLAYER_DARK

    def draw(self, surface):
        """
        绘制基础人形：
            身体（圆角矩形）、头部（圆）、眼睛、手臂、双腿。
            受击闪烁：hitstun_timer % 4 < 2 时整体用白色。
            死亡：整体旋转/压扁。
        """
        # 受击闪烁判定
        flash = self.hitstun_timer > 0 and (self.hitstun_timer % 4) < 2
        body_color = settings.WHITE if flash else self.get_body_color()
        dark_color = settings.WHITE if flash else self.get_dark_color()

        # 死亡时对整体做压扁 + 倾倒效果
        if self.dead:
            self._draw_dead(surface, body_color, dark_color)
            return

        x = int(self.x)
        y = int(self.y)
        w = self.width
        h = self.height
        cx = x + w // 2

        # ---- 双腿（奔跑摆动） ----
        leg_h = int(h * 0.32)
        leg_w = max(6, w // 5)
        leg_top = y + h - leg_h
        # 用 sin 做交替摆动；在地面且有水平速度时才有动画
        swing = 0.0
        if self.on_ground and abs(self.vx) > 0.5:
            swing = math.sin(self.anim_frame * 0.3) * (leg_w + 2)
        left_leg_x = cx - leg_w - 2 + int(swing)
        right_leg_x = cx + 2 - int(swing)
        pygame.draw.rect(surface, dark_color, (left_leg_x, leg_top, leg_w, leg_h))
        pygame.draw.rect(surface, dark_color, (right_leg_x, leg_top, leg_w, leg_h))

        # ---- 身体（圆角矩形） ----
        body_h = int(h * 0.46)
        body_w = int(w * 0.7)
        body_rect = pygame.Rect(cx - body_w // 2, leg_top - body_h, body_w, body_h)
        pygame.draw.rect(surface, body_color, body_rect, border_radius=8)

        # ---- 手臂（攻击时前伸） ----
        arm_w = max(6, w // 6)
        arm_h = int(body_h * 0.7)
        arm_y = body_rect.y + 6
        attacking = self.state_machine.current_name == "Attack"
        if attacking:
            # 前伸的手臂：朝 facing 方向伸出
            reach = int(w * 0.9)
            if self.facing == 1:
                arm_rect = pygame.Rect(body_rect.right - 2, arm_y, reach, arm_w)
            else:
                arm_rect = pygame.Rect(body_rect.left - reach + 2, arm_y, reach, arm_w)
        else:
            # 自然垂放，随奔跑轻微摆动
            back_arm_x = body_rect.left - arm_w + 2
            arm_rect = pygame.Rect(back_arm_x, arm_y, arm_w, arm_h)
        pygame.draw.rect(surface, dark_color, arm_rect, border_radius=4)

        # ---- 头部（圆形） ----
        head_r = int(w * 0.34)
        head_cx = cx
        head_cy = body_rect.y - head_r + 4
        pygame.draw.circle(surface, body_color, (head_cx, head_cy), head_r)

        # ---- 眼睛（小白点，随朝向偏移） ----
        eye_offset_x = int(head_r * 0.35) * self.facing
        eye_y = head_cy - int(head_r * 0.15)
        eye_r = max(2, head_r // 5)
        pygame.draw.circle(surface, settings.WHITE, (head_cx + eye_offset_x, eye_y), eye_r)
        pygame.draw.circle(surface, settings.WHITE, (head_cx + eye_offset_x + self.facing * eye_r * 2, eye_y), eye_r)

    def _draw_dead(self, surface, body_color, dark_color):
        """死亡绘制：整体压扁 + 倾倒（用 dead_timer 驱动）。"""
        # 压扁系数：随时间从 1 减小到 0.4
        squash = max(0.4, 1.0 - self.dead_timer * 0.02)
        w = int(self.width * (1.0 / squash) * 0.9)   # 横向拉伸
        h = int(self.height * squash)
        # 以脚底为基准绘制一个压扁的圆角矩形代表倒地角色
        cx = int(self.centerx)
        bottom = int(self.y + self.height)
        body_rect = pygame.Rect(cx - w // 2, bottom - h, w, h)
        pygame.draw.rect(surface, body_color, body_rect, border_radius=10)
        # 暗部描边
        pygame.draw.rect(surface, dark_color, body_rect, width=2, border_radius=10)

    # -------------------- 调试绘制 --------------------
    def draw_debug(self, surface):
        """绘制受击框（绿色线框）与攻击框（红色线框）。"""
        # 受击框：绿色
        pygame.draw.rect(surface, settings.GREEN, self.hurtbox, 1)
        # 碰撞体：灰色（可选，便于观察）
        pygame.draw.rect(surface, settings.GRAY, self.rect, 1)
        # 攻击框：红色
        if self.hitbox is not None:
            pygame.draw.rect(surface, settings.RED, self.hitbox, 2)