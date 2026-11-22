"""
particle.py —《英雄大作战 - 原型》粒子特效系统

提供：
    - Particle           单个粒子（位置/速度/生命/大小/颜色/重力/渐隐）
    - ParticleEffect     粒子组（批量发射/更新/绘制）
    - 预设特效函数        hit_spark / death_explosion / jump_dust /
                         run_dust / skill_charge / trail
    - 全局单例 effects    主循环直接调用 update_all / draw_all
    - camera             镜头震动对象（供战斗/弹道触发）

兼容旧接口（entity.py / projectile.py 已调用）：
    spawn(x, y, ...)             通用单粒子
    spawn_hit(x, y, blocked)     命中火花
    spawn_burst(x, y, count, color)  爆散
    spawn_skill(x, y, facing)    技能蓄力
    spawn_trail(x, y, color)     拖尾
    update_all() / draw_all(surface)

性能约束：
    单次发射粒子数 <= 30；全局粒子数上限 MAX_PARTICLES，超出时丢弃新增。
"""

import math
import random

import pygame

import settings


# ============================================================
# 全局上限（性能保护）
# ============================================================
MAX_PARTICLES = 600      # 全局粒子总数上限
MAX_EMIT_PER_CALL = 30   # 单次发射上限


# ============================================================
# 一、单个粒子
# ============================================================
class Particle:
    """
    单个粒子。
    生命周期 life 从 max_life 递减到 0；透明度 = life / max_life * 255。
    """

    def __init__(self, x, y, vx=0.0, vy=0.0,
                 life=20, size=4, color=(255, 255, 255),
                 gravity=False, fade=True, shape="circle"):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.life = life
        self.max_life = max(1, life)   # 防止除零
        self.size = float(size)
        self.color = color
        self.gravity = gravity
        self.fade = fade
        self.shape = shape             # "circle" / "square"

    @property
    def alive(self):
        """生命 > 0 即存活。"""
        return self.life > 0

    # -------------------- 更新 --------------------
    def update(self):
        """移动 + 受重力 + 递减生命。"""
        self.x += self.vx
        self.y += self.vy
        if self.gravity:
            self.vy += 0.3
        self.life -= 1

    # -------------------- 绘制 --------------------
    def draw(self, surface):
        """
        根据 life/max_life 计算透明度并绘制。
        使用 set_alpha 实现渐隐；尺寸随生命略微缩小，增强“消散”感。
        """
        if not self.alive:
            return

        # 透明度：满血 255 -> 消失 0
        ratio = self.life / self.max_life
        alpha = int(255 * ratio) if self.fade else 255
        alpha = max(0, min(255, alpha))
        if alpha <= 0:
            return

        # 尺寸随生命缩小（保留最小 1px）
        size = max(1, int(self.size * (0.5 + 0.5 * ratio)))

        # 用 SRCALPHA 临时表面画，再 blit，才能对形状生效 alpha
        d = size * 2 + 2
        tmp = pygame.Surface((d, d), pygame.SRCALPHA)
        if self.shape == "square":
            pygame.draw.rect(tmp, (*self.color[:3], alpha), (1, 1, size, size))
        else:
            pygame.draw.circle(tmp, (*self.color[:3], alpha),
                               (d // 2, d // 2), size)
        surface.blit(tmp, (int(self.x) - d // 2, int(self.y) - d // 2))


# ============================================================
# 二、粒子组
# ============================================================
class ParticleEffect:
    """
    粒子组管理器。
    所有粒子统一在 self.particles 里，供 update / draw 批处理。
    """

    def __init__(self):
        self.particles = []

    # -------------------- 发射 --------------------
    def emit(self, x, y, count=1, config=None):
        """
        在 (x, y) 发射 count 个粒子。

        config 可含键：
            speed_range  : (min, max)    粒子初速度
            angle_range  : (min, max)    发射角度（度）
            life_range   : (min, max)    生命周期帧数
            size_range   : (min, max)    初始大小
            color        : (r,g,b)       颜色
            gravity      : bool          是否受重力
            fade         : bool          是否渐隐
            shape        : "circle"/"square"
            converge     : bool          是否为“向中心汇聚”模式（速度方向指向中心）
        """
        config = config or {}

        # 性能保护：单次不超过 MAX_EMIT_PER_CALL，总数不超过 MAX_PARTICLES
        count = min(count, MAX_EMIT_PER_CALL)
        remain = MAX_PARTICLES - len(self.particles)
        if remain <= 0:
            return
        count = min(count, remain)

        speed_lo, speed_hi = config.get("speed_range", (1.0, 3.0))
        angle_lo, angle_hi = config.get("angle_range", (0, 360))
        life_lo, life_hi = config.get("life_range", (10, 20))
        size_lo, size_hi = config.get("size_range", (2, 5))
        color = config.get("color", (255, 255, 255))
        gravity = config.get("gravity", False)
        fade = config.get("fade", True)
        shape = config.get("shape", "circle")
        converge = config.get("converge", False)

        for _ in range(count):
            ang = math.radians(random.uniform(angle_lo, angle_hi))
            spd = random.uniform(speed_lo, speed_hi)
            vx = math.cos(ang) * spd
            vy = math.sin(ang) * spd

            if converge:
                # 汇聚模式：粒子从外围飞向中心（初始位置外扩，速度指向中心）
                radius = random.uniform(20, 40)
                px = x + math.cos(ang) * radius
                py = y + math.sin(ang) * radius
                # 速度方向指向中心
                vx = -math.cos(ang) * spd
                vy = -math.sin(ang) * spd
            else:
                px, py = x, y

            life = random.randint(int(life_lo), int(life_hi))
            size = random.uniform(size_lo, size_hi)

            self.particles.append(Particle(
                px, py, vx, vy, life, size, color, gravity, fade, shape
            ))

    # -------------------- 更新 --------------------
    def update(self):
        """更新所有粒子，清理死亡。"""
        for p in self.particles:
            p.update()
        # 原地过滤，避免频繁分配
        self.particles = [p for p in self.particles if p.alive]

    # -------------------- 绘制 --------------------
    def draw(self, surface):
        """绘制所有存活粒子。"""
        for p in self.particles:
            p.draw(surface)

    # -------------------- 清空 --------------------
    def clear(self):
        """清空所有粒子（切场景时用）。"""
        self.particles.clear()

    def count(self):
        """当前粒子数。"""
        return len(self.particles)


# ============================================================
# 三、镜头震动
# ============================================================
class Camera:
    """
    简易镜头震动。
        shake(magnitude, frames=5)：在指定帧数内产生随机偏移。
        offset：每帧读取的 (dx, dy) 偏移，供主循环统一平移画面。
    """
    def __init__(self):
        self._magnitude = 0.0
        self._frames = 0
        self.offset = (0, 0)

    def shake(self, magnitude=3.0, frames=5):
        """触发震动；多次触发取较大值，避免抵消。"""
        self._magnitude = max(self._magnitude, float(magnitude))
        self._frames = max(self._frames, int(frames))

    def update(self):
        """每帧更新偏移，帧数耗尽后归零。"""
        if self._frames > 0:
            import random as _r
            self.offset = (
                _r.uniform(-self._magnitude, self._magnitude),
                _r.uniform(-self._magnitude, self._magnitude),
            )
            self._frames -= 1
            if self._frames == 0:
                self._magnitude = 0.0
                self.offset = (0, 0)
        else:
            self.offset = (0, 0)


# ============================================================
# 四、全局单例
# ============================================================
effects = ParticleEffect()
camera = Camera()


# ============================================================
# 五、预设特效函数
# ============================================================
def hit_spark(x, y, direction=1):
    """
    命中火花。
    参数：
        x, y      命中位置
        direction 攻击方向（+1 右 / -1 左）；火花向反方向散射
    """
    # 向 direction 反向散射：direction=1 命中时火花向左飞（受击方被推离）
    base_angle = 180 if direction >= 0 else 0
    effects.emit(x, y, count=5, config={
        "speed_range": (3, 6),
        "angle_range": (base_angle - 45, base_angle + 45),
        "life_range": (10, 20),
        "size_range": (3, 5),
        "color": settings.WHITE,
        "gravity": False,
    })


def death_explosion(x, y, color=(255, 100, 80)):
    """
    死亡爆散。
    参数：
        x, y   爆散中心
        color  粒子颜色（默认橙红）
    """
    effects.emit(x, y, count=20, config={
        "speed_range": (2, 8),
        "angle_range": (0, 360),
        "life_range": (20, 40),
        "size_range": (4, 8),
        "color": color,
        "gravity": True,
    })


def jump_dust(x, y, direction=1):
    """
    跳跃尘土。
    参数：
        x, y      起跳位置（通常为脚底）
        direction 起跳朝向；尘土向后下方飘散
    """
    base_angle = 135 if direction >= 0 else 45   # 后方下向
    effects.emit(x, y, count=6, config={
        "speed_range": (1, 3),
        "angle_range": (base_angle - 30, base_angle + 30),
        "life_range": (15, 15),
        "size_range": (3, 6),
        "color": (180, 180, 170),
        "gravity": True,
    })


def run_dust(x, y, direction=1):
    """
    奔跑尘土。
    参数：
        x, y      脚底位置
        direction 奔跑朝向；尘土向后飘散
    """
    base_angle = 180 if direction >= 0 else 0
    effects.emit(x, y, count=2, config={
        "speed_range": (1, 2),
        "angle_range": (base_angle - 20, base_angle + 20),
        "life_range": (10, 10),
        "size_range": (2, 4),
        "color": (200, 200, 190),
        "gravity": False,
    })


def skill_charge(x, y, color=(60, 120, 230)):
    """
    技能蓄力。
    参数：
        x, y   蓄力中心
        color  粒子颜色
    效果：粒子从四周向中心汇聚。
    """
    effects.emit(x, y, count=8, config={
        "speed_range": (2, 4),
        "angle_range": (0, 360),
        "life_range": (15, 15),
        "size_range": (2, 4),
        "color": color,
        "gravity": False,
        "converge": True,
    })


def trail(x, y, color=(255, 255, 255)):
    """
    拖尾。
    参数：
        x, y   拖尾位置
        color  粒子颜色
    效果：原地静止、快速消失。
    """
    effects.emit(x, y, count=1, config={
        "speed_range": (0, 0.2),
        "angle_range": (0, 360),
        "life_range": (8, 8),
        "size_range": (4, 4),
        "color": color,
        "gravity": False,
    })


def burst(x, y, count=10, color=(255, 255, 255)):
    """
    通用爆散（供 projectile 命中调用）。
    参数：
        x, y   爆散中心
        count  数量（内部自动裁剪到 <= 30）
        color  颜色
    """
    effects.emit(x, y, count=count, config={
        "speed_range": (2, 6),
        "angle_range": (0, 360),
        "life_range": (12, 25),
        "size_range": (3, 6),
        "color": color,
        "gravity": True,
    })


# ============================================================
# 六、兼容旧接口（entity.py / player.py / projectile.py 已调用）
# ============================================================
def spawn(x, y, vx=None, vy=None, color=None, **kwargs):
    """
    通用“生成一个粒子”。
    兼容两种调用方式：
        spawn(x, y)                              随机方向
        spawn(x, y, vx, vy)                      指定速度
        spawn(x, y, color=(r,g,b))               指定颜色
    参数：
        x, y       位置
        vx, vy     可选速度（缺省时随机 1-3）
        color      可选颜色
    """
    if vx is None:
        ang = random.uniform(0, math.tau)
        spd = random.uniform(1.0, 3.0)
        vx = math.cos(ang) * spd
        vy = math.sin(ang) * spd if vy is None else vy
    if vy is None:
        vy = random.uniform(-1.5, 1.5)

    effects.emit(x, y, count=1, config={
        "speed_range": (0, 0),
        "angle_range": (0, 0),
        "life_range": (12, 20),
        "size_range": (2, 4),
        "color": color or (255, 255, 255),
    })
    # 上面 emit 生成的后追加粒子速度需要修正为指定 vx/vy
    if effects.particles:
        p = effects.particles[-1]
        p.vx = vx
        p.vy = vy


def spawn_hit(x, y, blocked=False):
    """
    命中特效（entity.take_damage 调用）。
    参数：
        x, y     命中位置
        blocked  是否被防御（防御时用别的颜色与更少火花）
    """
    if blocked:
        effects.emit(x, y, count=4, config={
            "speed_range": (2, 4),
            "angle_range": (0, 360),
            "life_range": (8, 14),
            "size_range": (2, 4),
            "color": (120, 200, 255),
            "gravity": False,
        })
    else:
        hit_spark(x, y, direction=1)


def spawn_burst(x, y, count=10, color=(255, 255, 255)):
    """兼容 projectile.py 的 spawn_burst 调用。"""
    burst(x, y, count=count, color=color)


def spawn_skill(x, y, facing=1):
    """兼容 player.release_skill 的 spawn_skill 调用。"""
    skill_charge(x, y)


def spawn_trail(x, y, color=(255, 255, 255)):
    """兼容 projectile.EnergyBall 的 spawn_trail 调用。"""
    trail(x, y, color)


def update_all():
    """
    兼容 main.py 的 update_particles()：
    更新粒子 + 更新镜头震动偏移。
    """
    effects.update()
    camera.update()


def draw_all(surface):
    """兼容 main.py 的 draw_particles()。"""
    effects.draw(surface)


def clear_all():
    """清空所有粒子（切场景用）。"""
    effects.clear()


# ============================================================
# 简单测试：直接运行本文件可观察特效
# ============================================================
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((settings.WIDTH, settings.HEIGHT))
    pygame.display.set_caption("粒子特效测试 - 点击发射")
    clock = pygame.time.Clock()
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos
                death_explosion(mx, my)
                camera.shake(5, frames=5)

        update_all()
        screen.fill(settings.SKY_BLUE)
        draw_all(screen)
        pygame.display.flip()
        clock.tick(settings.FPS)
    pygame.quit()