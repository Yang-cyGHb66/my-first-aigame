"""
states.py —《英雄大作战 - 原型》角色状态机
采用状态模式（State Pattern）：每个状态是独立类，实现 enter / update / exit。

约定（entity 需要提供的属性/方法）：
    属性:
        x, y            : 位置坐标（float）
        vx, vy          : 速度（float）
        facing          : 朝向 +1 右 / -1 左
        on_ground       : 是否站在地面上
        hp, mp, sp      : 当前属性值
        input           : 输入对象（提供 left/right/jump/attack/block 等布尔值）
        hitbox          : 当前攻击判定框（None 表示无）
    方法:
        get_input()     : 返回输入快照
        spawn_hitbox()  : 生成攻击判定框
        consume_hit()   : 是否本帧被命中（供受击状态判断，可选）
所有对 pygame 的依赖都在 game loop 内完成，本文件不 import pygame。
"""

from settings import (
    GRAVITY, AIR_CONTROL, FRICTION,
    PLAYER_SPEED, RUN_SPEED, JUMP_VELOCITY,
    ATTACK_STARTUP, ATTACK_ACTIVE, ATTACK_RECOVERY, COMBO_WINDOW,
    HITSTUN, BLOCK_REDUCTION,
    HP_MAX, SP_JUMP_COST, SP_RUN_COST,
)


# ============================================================
# 一、状态基类
# ============================================================
class State:
    """所有状态的基类，定义统一接口。"""

    # 状态名称（用于调试/打印）
    name = "State"

    def enter(self, entity):
        """进入状态时调用一次。"""
        pass

    def update(self, entity):
        """
        每帧更新状态逻辑。
        返回:
            下一个状态类（切换）
            None（保持当前状态）
        """
        return None

    def exit(self, entity):
        """离开状态时调用一次，用于清理。"""
        pass

    def can_transition(self, entity, new_state):
        """判断能否切换到 new_state（子类可覆盖做特殊限制）。"""
        return True

    def __repr__(self):
        return f"<{self.name}>"


# ============================================================
# 二、站立状态
# ============================================================
class IdleState(State):
    """
    站立状态：
        - 每帧应用地面摩擦力，水平速度逐渐归零
        - 输入左右    -> RunState（若站在地面）
        - 输入跳跃    -> JumpState
        - 输入攻击    -> AttackState
        - 输入防御    -> BlockState
        - 若离地      -> FallState（例如被击飞或走下平台）
    """
    name = "Idle"

    def enter(self, entity):
        entity.hitbox = None

    def update(self, entity):
        # 应用地面摩擦力，让角色平滑停下
        entity.vx *= FRICTION
        if abs(entity.vx) < 0.1:
            entity.vx = 0

        inp = entity.get_input()

        # 若不在空中，才允许地面移动类转换
        if entity.on_ground:
            # 防御优先（按住防御键）
            if inp.get("block"):
                return BlockState
            # 攻击
            if inp.get("attack"):
                return AttackState
            # 跳跃
            if inp.get("jump"):
                return JumpState
            # 左右移动 -> 奔跑
            if inp.get("left") or inp.get("right"):
                return RunState
        else:
            # 空中则进入下落状态
            return FallState

        return None   # 保持站立

    def can_transition(self, entity, new_state):
        return True


# ============================================================
# 三、奔跑状态
# ============================================================
class RunState(State):
    """
    奔跑状态：
        - 按方向移动，并更新朝向
        - 每帧消耗 SP（SP_RUN_COST）；SP 耗尽则降速为行走
        - 松开方向键 -> IdleState
        - 跳跃       -> JumpState
        - 攻击       -> AttackState
        - 离地       -> FallState
    """
    name = "Run"

    def enter(self, entity):
        entity.hitbox = None

    def update(self, entity):
        inp = entity.get_input()

        # 离地则转下落
        if not entity.on_ground:
            return FallState

        direction = 0
        if inp.get("left"):
            direction = -1
        elif inp.get("right"):
            direction = 1

        # 松开方向 -> 站立
        if direction == 0:
            return IdleState

        # 更新朝向
        entity.facing = direction

        # 奔跑持续消耗体力
        if entity.sp > 0:
            entity.sp = max(0, entity.sp - SP_RUN_COST)
            speed = RUN_SPEED
        else:
            speed = PLAYER_SPEED   # 体力耗尽只能走

        entity.vx = direction * speed

        # 其它动作转换
        if inp.get("block"):
            return BlockState
        if inp.get("attack"):
            return AttackState
        if inp.get("jump"):
            return JumpState

        return None


# ============================================================
# 四、跳跃上升状态
# ============================================================
class JumpState(State):
    """
    跳跃上升：
        - 进入时赋予跳跃初速度 JUMP_VELOCITY（由 enter 处理）
        - 每帧施加重力
        - 空中水平微调（速度乘 AIR_CONTROL）
        - 支持二段跳：再次跳跃且未用过二段跳时，消耗 20 SP 重新上跳
        - vy >= 0 时转 FallState
    """
    name = "Jump"
    DOUBLE_JUMP_COST = 20   # 二段跳体力消耗

    def enter(self, entity):
        entity.hitbox = None
        entity.on_ground = False
        # 首次进入（从地面起跳）赋初速度
        if not getattr(entity, "_jump_consumed", False):
            entity.vy = JUMP_VELOCITY
        entity._double_jump_used = False   # 重置二段跳标记

    def update(self, entity):
        # 施加重力
        entity.vy += GRAVITY

        inp = entity.get_input()

        # 空中水平微调
        move = 0
        if inp.get("left"):
            move = -1
        elif inp.get("right"):
            move = 1
        if move != 0:
            entity.facing = move
            entity.vx = move * PLAYER_SPEED * AIR_CONTROL

        # 二段跳：上升或下落中都可以触发（此处仅在上升时检测）
        if inp.get("jump") and not entity._double_jump_used and entity.sp >= self.DOUBLE_JUMP_COST:
            entity.sp -= self.DOUBLE_JUMP_COST
            entity.vy = JUMP_VELOCITY
            entity._double_jump_used = True
            entity._jump_consumed = True
            return None

        # 开始下落 -> FallState
        if entity.vy >= 0:
            return FallState

        # 攻击 -> 空中攻击
        if inp.get("attack"):
            return AttackState

        return None


# ============================================================
# 五、下落状态
# ============================================================
class FallState(State):
    """
    下落状态：
        - 每帧施加重力，空中水平微调
        - 落地 -> IdleState
        - 攻击 -> AttackState（跳跃攻击）
        - 支持二段跳（下落时也可以补跳）
    """
    name = "Fall"

    def enter(self, entity):
        entity.hitbox = None

    def update(self, entity):
        entity.vy += GRAVITY   # 施加重力

        inp = entity.get_input()

        # 空中水平微调
        move = 0
        if inp.get("left"):
            move = -1
        elif inp.get("right"):
            move = 1
        if move != 0:
            entity.facing = move
            entity.vx = move * PLAYER_SPEED * AIR_CONTROL

        # 二段跳（若尚未使用）
        if inp.get("jump") and not getattr(entity, "_double_jump_used", False) and entity.sp >= JumpState.DOUBLE_JUMP_COST:
            entity.sp -= JumpState.DOUBLE_JUMP_COST
            entity.vy = JUMP_VELOCITY
            entity._double_jump_used = True
            return JumpState

        # 落地 -> 站立
        if entity.on_ground:
            entity.vy = 0
            entity._double_jump_used = False
            entity._jump_consumed = False
            return IdleState

        # 空中攻击
        if inp.get("attack"):
            return AttackState

        return None


# ============================================================
# 六、攻击状态
# ============================================================
class AttackState(State):
    """
    攻击状态（三段连招）：
        - 阶段划分：前摇(ATTACK_STARTUP) -> 判定(ATTACK_ACTIVE) -> 后摇(ATTACK_RECOVERY)
        - 判定阶段生成 hitbox
        - 连招：后摇阶段内按攻击键且未超过 COMBO_WINDOW -> 进入下一段（最多 3 段）
        - 第三段结束 或 无后续输入 -> IdleState
    内部使用 _phase 记录当前阶段，_timer 记录阶段剩余帧。
    """
    name = "Attack"
    MAX_COMBO = 3   # 最大连段数

    def enter(self, entity):
        # 首次进入攻击（从其它状态来）初始化为第 1 段前摇
        if not getattr(entity, "_attack_in_progress", False):
            entity._attack_in_progress = True
            entity._combo_index = 1
            entity._phase = "startup"
            entity._timer = ATTACK_STARTUP
            entity._combo_buffer = 0
        entity.vx = 0    # 攻击时停止水平移动
        entity.hitbox = None

    def update(self, entity):
        inp = entity.get_input()
        entity._timer -= 1

        # 记录连招缓冲
        if inp.get("attack"):
            entity._combo_buffer = COMBO_WINDOW

        # 前摇阶段
        if entity._phase == "startup":
            if entity._timer <= 0:
                entity._phase = "active"
                entity._timer = ATTACK_ACTIVE
                entity.spawn_hitbox()   # 判定阶段生成 hitbox

        # 判定阶段
        elif entity._phase == "active":
            if entity._timer <= 0:
                entity._phase = "recovery"
                entity._timer = ATTACK_RECOVERY
                entity.hitbox = None

        # 后摇阶段
        elif entity._phase == "recovery":
            if entity._combo_buffer > 0:
                entity._combo_buffer -= 1
            if entity._timer <= 0:
                # 后摇结束：若在连招窗口内按了攻击且未到最大段数 -> 下一段
                if entity._combo_buffer > 0 and entity._combo_index < self.MAX_COMBO:
                    entity._combo_index += 1
                    entity._phase = "startup"
                    entity._timer = ATTACK_STARTUP
                    entity._combo_buffer = 0
                    return None
                # 否则结束整个攻击
                self._cleanup(entity)
                return IdleState if entity.on_ground else FallState

        return None

    def exit(self, entity):
        entity.hitbox = None

    def _cleanup(self, entity):
        entity._attack_in_progress = False
        entity._combo_index = 0
        entity._phase = None
        entity._combo_buffer = 0


# ============================================================
# 七、受击硬直状态
# ============================================================
class HurtState(State):
    """
    受击硬直：
        - 持续 HITSTUN 帧，期间无法操作
        - 应用击退速度（由外部在 enter 前设置 vx/vy）与重力
        - 结束后 -> IdleState（在地面）或 FallState（在空中）
        - HP <= 0 -> DeadState
    """
    name = "Hurt"

    def enter(self, entity):
        entity.hitbox = None
        entity._hitstun_timer = HITSTUN

    def update(self, entity):
        # 死亡检查
        if entity.hp <= 0:
            return DeadState

        # 施加重力（击退的垂直速度已在外部设置）
        entity.vy += GRAVITY

        # 硬直计时
        entity._hitstun_timer -= 1
        if entity._hitstun_timer <= 0:
            entity._hitstun_timer = 0
            return IdleState if entity.on_ground else FallState

        return None


# ============================================================
# 八、防御状态
# ============================================================
class BlockState(State):
    """
    防御：
        - 按住防御键保持；松开转 IdleState
        - 无法移动
        - 受击时伤害乘 BLOCK_REDUCTION（伤害计算由外部 apply_damage 处理）
        - 受击不进入 HurtState（角色保持防御）
    """
    name = "Block"

    def enter(self, entity):
        entity.hitbox = None
        entity.vx = 0
        entity.is_blocking = True

    def update(self, entity):
        inp = entity.get_input()

        # 按住防御保持，松开转站立
        if not inp.get("block"):
            return IdleState

        # 防御时无法移动
        entity.vx = 0
        return None

    def exit(self, entity):
        entity.is_blocking = False


# ============================================================
# 九、死亡状态
# ============================================================
class DeadState(State):
    """
    死亡：
        - 播放倒地效果（旋转或压扁，由渲染层根据 entity.dead_timer 处理）
        - 完全不可操作
        - 持续若干帧后停留在死亡姿势（不自动切换）
    """
    name = "Dead"

    def enter(self, entity):
        entity.hitbox = None
        entity.dead = True
        entity.dead_timer = 0
        entity.vx = 0
        entity.is_blocking = False

    def update(self, entity):
        # 死亡动画计时（渲染层用 dead_timer 计算旋转/缩放）
        entity.dead_timer += 1
        # 应用重力让尸体落地
        entity.vy += GRAVITY
        return None


# ============================================================
# 十、状态管理器
# ============================================================
class StateMachine:
    """
    状态机管理器：
        - __init__(owner, initial_state)：绑定所属实体与初始状态
        - change_state(new_state_class)：exit 旧状态 -> 实例化并 enter 新状态
        - update()：每帧驱动当前状态，处理转换
        - current：当前状态实例
    """

    def __init__(self, owner, initial_state):
        self.owner = owner
        self.current = None
        self.change_state(initial_state)

    def change_state(self, new_state_class):
        """切换到新状态类（传类，不是实例）。"""
        # 合法性检查
        if self.current is not None:
            if not self.current.can_transition(self.owner, new_state_class):
                return
            self.current.exit(self.owner)

        # 实例化并进入
        self.current = new_state_class()
        self.current.enter(self.owner)

    def update(self):
        """驱动当前状态；若返回新状态类则执行切换。"""
        if self.current is None:
            return
        next_state = self.current.update(self.owner)
        if next_state is not None and next_state is not self.current.__class__:
            self.change_state(next_state)

    @property
    def current_name(self):
        return self.current.name if self.current else "None"


# ============================================================
# 简单测试：打印所有状态名
# ============================================================
if __name__ == "__main__":
    # 收集本模块内所有 State 子类
    all_states = [
        cls for cls in globals().values()
        if isinstance(cls, type) and issubclass(cls, State) and cls is not State
    ]
    print("已定义的状态类：")
    for cls in sorted(all_states, key=lambda c: c.name):
        print(f"  - {cls.__name__:<14} name={cls.name!r}")
    print(f"共 {len(all_states)} 个状态（不含基类 State）。")