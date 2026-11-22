"""
projectile.py —《英雄大作战 - 原型》弹道系统

提供：
    - Projectile          弹道基类（位置/速度/生命周期/包围盒/命中回调）
    - EnergyBall          能量弹（三层同心圆 + 拖尾 + 爆散特效）
    - Arrow               箭矢（线段 + 三角箭头 + 随速度旋转）
    - ProjectileManager   统一管理弹道更新、碰撞、绘制、清理

全局约定：
    PROJECTILES = []      兼容 player.py 的“注册到全局弹体列表”逻辑

依赖：
    - settings.py   常量
    - particle.py   粒子与镜头（可选，缺失时静默降级）
"""

import math

import pygame

import settings

# ---- 可选依赖：粒子模块（缺失时降级） ----
try:
    import particle as particle_module
except Exception:  # pragma: no cover
    particle_module = None


# ============================================================
# 全局弹道列表（兼容 player.release_skill 的注册方式）
# ============================================================
PROJECTILES = []


# ============================================================
# 一、弹道基类
# ============================================================
class Projectile:
    """
    弹道基类：
        - 统一的移动 / 生命周期 / 包围盒 / 命中处理
        - 子类只需重写 draw() 与（原可选的）on_hit()
    """

    def __init__(self, x, y, vx=0.0, vy=0.0,
                 radius=8, damage=0, owner=None,
                 lifetime=60, color=settings.WHITE):
        self.x = float(x)          # 中心坐标 X
        self.y = float(y)          # 中心坐标 Y
        self.vx = float(vx)        # 水平速度
        self.vy = float(vy)        # 垂直速度
        self.radius = radius       # 半径（用于绘制与包围盒）
        self.damage = damage       # 伤害值
        self.owner = owner         # 发射者（用于跳过自身碰撞）
        self.lifetime = lifetime   # 剩余存活帧数
        self.color = color         # 主色调
        self.active = True         # 是否存活

    # -------------------- 几何 --------------------
    @property
    def rect(self):
        """
        返回包围盒 Rect（以中心点向外扩展 radius）。
        注意：pygame.Rect 使用整数坐标，这里取 int 保证碰撞稳定。
        """
        r = self.radius
        return pygame.Rect(
            int(self.x - r),
            int(self.y - r),
            int(r * 2),
            int(r * 2),
        )

    # -------------------- 更新 --------------------
    def update(self):
        """
        每帧更新：
            1. 位置 += 速度
            2. lifetime -= 1
            3. 超出屏幕 或 生命耗尽 -> active = False
        """
        self.x += self.vx
        self.y += self.vy
        self.lifetime -= 1

        # 生命耗尽
        if self.lifetime <= 0:
            self.active = False

        # 出屏判定（留 60 像素裕量，避免“半出屏即消失”的突兀感）
        margin = 60
        if (self.x < -margin or self.x > settings.WIDTH + margin or
                self.y < -margin or self.y > settings.HEIGHT + margin):
            self.active = False

    # -------------------- 绘制 --------------------
    def draw(self, surface):
        """基类默认画一个实心圆，子类重写。"""
        pygame.draw.circle(surface, self.color,
                           (int(self.x), int(self.y)), self.radius)

    # -------------------- 命中 --------------------
    def on_hit(self, target):
        """
        命中处理，默认对 target 造成伤害。
        由于 owner 判断已在 Manager 层做过滤，这里不再重复判断。
        子类可覆盖以追加特效或特殊逻辑。
        """
        if target is None:
            return
        target.take_damage(self.damage, attacker=self.owner, knockback=True)

    # -------------------- 工具 --------------------
    def _emit(self, method_name, *args, **kwargs):
        """便捷调用 particle 模块的方法（容错）。"""
        if particle_module is None:
            return
        fn = getattr(particle_module, method_name, None)
        if fn is None:
            # 退化到通用 spawn
            fn = getattr(particle_module, "spawn", None)
        if fn is None:
            return
        try:
            fn(*args, **kwargs)
        except Exception:
            pass

    def _shake(self, magnitude, frames=5):
        """触发镜头震动（若 particle.camera 提供 shake）。"""
        if particle_module is None:
            return
        camera = getattr(particle_module, "camera", None)
        if camera is not None and hasattr(camera, "shake"):
            try:
                camera.shake(magnitude, frames=frames)
            except TypeError:
                try:
                    camera.shake(magnitude)
                except Exception:
                    pass
            except Exception:
                pass


# ============================================================
# 二、能量弹
# ============================================================
class EnergyBall(Projectile):
    """
    能量弹（技能弹体）：
        - radius=12, damage=DMG_SKILL, lifetime=60
        - 绘制三层同心圆：外圈半透明/中圈主色/内圈白色
        - 每帧生成一个拖尾粒子
        - 命中时爆散 10 个粒子 + 镜头震动
    """

    def __init__(self, x, y, direction=1, speed=12, damage=None, owner=None):
        super().__init__(
            x=x, y=y,
            vx=direction * speed, vy=0.0,
            radius=12,
            damage=damage if damage is not None else settings.DMG_SKILL,
            owner=owner,
            lifetime=60,
            color=settings.MP_BLUE,
        )
        self.direction = direction    # 供 enemy 检测弹道方向使用
        self._angle = 0.0             # 内圈旋转角度（视觉细节）

    # -------------------- 更新 --------------------
    def update(self):
        super().update()

        # 每帧拖尾：在当前位置生成一个小粒子
        if self.active and particle_module is not None:
            sp = getattr(particle_module, "spawn_trail", None)
            if sp is not None:
                try:
                    sp(self.x, self.y, self.color)
                except Exception:
                    pass
            else:
                self._emit("spawn", self.x, self.y)

        # 内圈旋转
        self._angle = (self._angle + 8) % 360

    # -------------------- 绘制 --------------------
    def draw(self, surface):
        """三层同心圆：外层半透明光晕 + 中层主色 + 内层白核。"""
        cx, cy = int(self.x), int(self.y)
        r = self.radius

        # 外层：半透明光晕（用带 alpha 的临时 surface 实现）
        glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        gx, gy = r * 2, r * 2
        pygame.draw.circle(glow, (*self.color[:3], 90), (gx, gy), int(r * 1.8))
        surface.blit(glow, (cx - r * 2, cy - r * 2))

        # 中层：主色实心圆
        pygame.draw.circle(surface, self.color, (cx, cy), r)

        # 内层：白色核心（略小，略有偏心制造高光感）
        pygame.draw.circle(surface, settings.WHITE, (cx - 1, cy - 1), max(2, r // 2))

    # -------------------- 命中 --------------------
    def on_hit(self, target):
        """命中：先造成伤害，再爆散粒子 + 镜头震动。"""
        # 造成伤害
        super().on_hit(target)

        # 爆散 10 个粒子
        if particle_module is not None:
            burst = getattr(particle_module, "spawn_burst", None)
            if burst is not None:
                try:
                    burst(self.x, self.y, count=10, color=self.color)
                except TypeError:
                    try:
                        burst(self.x, self.y, 10)
                    except Exception:
                        pass
                except Exception:
                    pass
            else:
                # 退化：逐个调用 spawn，随机散开
                import random
                for _ in range(10):
                    ang = random.uniform(0, math.tau)
                    dx = math.cos(ang) * random.uniform(1, 4)
                    dy = math.sin(ang) * random.uniform(1, 4)
                    self._emit("spawn", self.x, self.y, dx, dy)

        # 镜头震动
        self._shake(5, frames=5)


# ============================================================
# 三、箭矢
# ============================================================
class Arrow(Projectile):
    """
    箭矢：
        - 长度 30，宽度 4，damage=12，lifetime=80
        - 绘制：线段 + 三角形箭头，根据 vx/vy 计算旋转角度
    """

    LENGTH = 30   # 箭身长度（像素）
    WIDTH = 4     # 箭身宽度（像素）

    def __init__(self, x, y, vx=8.0, vy=0.0, owner=None):
        super().__init__(
            x=x, y=y,
            vx=vx, vy=vy,
            radius=self.LENGTH // 2,   # 用长度一半作为包围盒半径
            damage=12,
            owner=owner,
            lifetime=80,
            color=(200, 180, 120),
        )
        # 计算朝向角度（度），供绘制与调试使用
        self.angle = math.degrees(math.atan2(self.vy, self.vx))

    # -------------------- 更新 --------------------
    def update(self):
        super().update()
        # 若速度变化（例如子类引入重力），角度需每帧刷新
        if self.vx or self.vy:
            self.angle = math.degrees(math.atan2(self.vy, self.vx))

    # -------------------- 绘制 --------------------
    def draw(self, surface):
        """
        绘制箭矢：
            以中心为原点，沿速度方向画一条线段 + 三角形箭头。
            使用局部坐标顶点旋转，避免频繁创建 Surface。
        """
        # 单位方向向量与垂直向量
        if self.vx or self.vy:
            length = math.hypot(self.vx, self.vy)
            dx, dy = self.vx / length, self.vy / length
        else:
            dx, dy = 1.0, 0.0
        # 垂直方向（用于箭身宽度）
        px, py = -dy, dx

        half = self.LENGTH / 2
        half_w = self.WIDTH / 2

        # 尾端点与头部端点
        tail = (self.x - dx * half, self.y - dy * half)
        head = (self.x + dx * half, self.y + dy * half)

        # 箭身线段
        pygame.draw.line(surface, self.color,
                         (int(tail[0]), int(tail[1])),
                         (int(head[0]), int(head[1])),
                         self.WIDTH)

        # 三角箭头（三个点）
        tip = (self.x + dx * (half + 8), self.y + dy * (half + 8))
        left = (self.x + dx * (half - 2) + px * half_w * 2,
                self.y + dy * (half - 2) + py * half_w * 2)
        right = (self.x + dx * (half - 2) - px * half_w * 2,
                 self.y + dy * (half - 2) - py * half_w * 2)
        pygame.draw.polygon(surface, self.color, [
            (int(tip[0]), int(tip[1])),
            (int(left[0]), int(left[1])),
            (int(right[0]), int(right[1])),
        ])

        # 尾羽（两条短线）
        feather_back = (self.x - dx * (half + 2), self.y - dy * (half + 2))
        for sign in (1, -1):
            fb = (feather_back[0] + px * half_w * sign * 2,
                  feather_back[1] + py * half_w * sign * 2)
            pygame.draw.line(surface, (160, 130, 90),
                             (int(feather_back[0]), int(feather_back[1])),
                             (int(fb[0]), int(fb[1])), 2)

    # -------------------- 命中 --------------------
    def on_hit(self, target):
        """命中：造成伤害并生成少量火花。"""
        super().on_hit(target)
        if particle_module is not None:
            burst = getattr(particle_module, "spawn_burst", None)
            if burst is not None:
                try:
                    burst(self.x, self.y, count=5, color=self.color)
                except TypeError:
                    try:
                        burst(self.x, self.y, 5)
                    except Exception:
                        pass
                except Exception:
                    pass
            else:
                for _ in range(5):
                    self._emit("spawn", self.x, self.y)


# ============================================================
# 四、弹道管理器
# ============================================================
class ProjectileManager:
    """
    统一管理弹道：
        - projectiles 列表
        - add / update / draw / clear
        - 更新时自动与“非 owner 实体”碰撞检测

    碰撞检测逻辑：
        遍历每个弹道，对每个实体：
            1. 跳过 owner 本身（防止自己打自己）
            2. 跳过已死亡实体（take_damage 内部也会判断，但这里提前过滤省开销）
            3. 用 projectile.rect 与 entity.hurtbox 做 colliderect
            4. 命中则调用 on_hit(entity) 并置 active=False，跳出内层循环
        （当前设计：一个弹道只命中一个目标。若需穿透，改为不 break 并管理命中集合。）
    """

    def __init__(self):
        self.projectiles = []

    # -------------------- 添加 --------------------
    def add(self, projectile):
        """添加弹道，同时同步到全局 PROJECTILES，兼容 player.py 的注册方式。"""
        self.projectiles.append(projectile)
        # 若 player.py 曾把同一实例追加到全局列表，避免重复添加
        if projectile not in PROJECTILES:
            PROJECTILES.append(projectile)
        return projectile

    # -------------------- 更新 --------------------
    def update(self, entities):
        """
        更新所有弹道并做碰撞检测。
        参数：
            entities: 可碰撞实体列表（玩家、敌人等），需提供 hurtbox 与 take_damage
        """
        for proj in list(self.projectiles):
            # 已失效的弹道：跳过但先保留，clear() 负责移除
            if not proj.active:
                continue

            # 1) 移动与生命周期
            proj.update()

            # 更新后如果已失效（出屏/超时），直接跳过碰撞
            if not proj.active:
                continue

            # 2) 碰撞检测
            proj_rect = proj.rect
            for entity in entities:
                # 跳过自身发射者
                if entity is proj.owner:
                    continue
                # 跳过已死亡实体
                if getattr(entity, "dead", False):
                    continue
                # 跳过无 hurtbox 的对象
                hurtbox = getattr(entity, "hurtbox", None)
                if hurtbox is None:
                    continue

                # 命中判定：包围盒与受击框相交即算命中
                if proj_rect.colliderect(hurtbox):
                    proj.on_hit(entity)     # 造成伤害 / 播放特效
                    proj.active = False     # 标记失效
                    break                   # 一个弹道只命中一个目标

    # -------------------- 绘制 --------------------
    def draw(self, surface):
        """绘制所有存活弹道。"""
        for proj in self.projectiles:
            if proj.active:
                try:
                    proj.draw(surface)
                except Exception:
                    # 绘制异常不应中断主循环
                    pass

    # -------------------- 清理 --------------------
    def clear(self):
        """
        清除不活跃的弹道：
            - 从 self.projectiles 中移除
            - 同步从全局 PROJECTILES 中移除
        """
        self.projectiles = [p for p in self.projectiles if p.active]
        # 复用同一实例，避免外部持有 PROJECTILES 引用失效
        PROJECTILES[:] = [p for p in PROJECTILES if p.active]

    # -------------------- 查询 --------------------
    def count(self):
        """活跃弹道数。"""
        return sum(1 for p in self.projectiles if p.active)


# ============================================================
# 便捷函数（可选）：供 player.py / enemy.py 直接调用
# ============================================================
_DEFAULT_MANAGER = None


def get_manager():
    """获取全局默认管理器（惰性创建）。"""
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = ProjectileManager()
    return _DEFAULT_MANAGER


def spawn_energy_ball(x, y, direction, owner, speed=12, damage=None):
    """便捷：生成一枚能量弹并注册。"""
    ball = EnergyBall(x, y, direction=direction, speed=speed,
                      damage=damage, owner=owner)
    get_manager().add(ball)
    return ball


def spawn_arrow(x, y, vx=8.0, vy=0.0, owner=None):
    """便捷：生成一支箭矢并注册。"""
    arrow = Arrow(x, y, vx=vx, vy=vy, owner=owner)
    get_manager().add(arrow)
    return arrow