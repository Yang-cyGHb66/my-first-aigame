"""
camera.py —《英雄大作战 - 原型》镜头跟随与震动

提供：
    - Camera    镜头类（平滑跟随 + 震动 + 世界坐标转屏幕坐标 + 可见区域）
    - camera    全局实例占位（None，由 main.py 初始化）

设计要点：
    1. 平滑跟随：offset 每帧向“目标-屏幕中心”的差值做 10% 线性插值（lerp）
       公式: offset += (desired - offset) * SMOOTH
       这样镜头会“追”着目标走，产生柔软跟随感，而非硬贴。
    2. 震动：每帧生成随机偏移，帧数递减、强度按 decay 衰减，
       叠加在跟随 offset 之上，跟随与震动互不干扰。
    3. 边界限制：offset 被 clamp 在 bounds 内，避免看到世界外的空白。

兼容说明：
    particle.py 里有一个轻量 Camera（仅 shake/offset），entity/projectile
    通过 `particle.camera.shake()` 触发震动。为避免两套相机冲突，
    本模块在 __init__ 时可选择性把自身挂到 particle.camera 上（见下方 bridge）。
"""

import random

import pygame

import settings


# ============================================================
# 镜头类
# ============================================================
class Camera:
    """
    镜头：
        负责把“世界坐标”映射到“屏幕坐标”，并实现平滑跟随与震动。
    """

    # 平滑跟随系数：越大越硬，越小越软（0.1 为常用手感）
    SMOOTH = 0.1

    def __init__(self, target=None, bounds=None):
        """
        参数：
            target  跟随目标（需有 centerx / x / width / y / height 属性）
            bounds  世界边界 pygame.Rect，用于限制镜头可见范围；
                    为 None 时默认使用整个游戏世界 (0,0,WIDTH,HEIGHT)
        """
        self.target = target

        # 跟随偏移量（世界坐标系下镜头左上角的偏移）
        self.offset_x = 0.0
        self.offset_y = 0.0

        # 震动参数
        self.shake_intensity = 0.0    # 当前震动强度
        self.shake_duration = 0       # 剩余震动帧数
        self.shake_decay = 0.9        # 每帧衰减系数
        self._shake_offset_x = 0.0    # 本帧震动偏移（随机）
        self._shake_offset_y = 0.0

        # 镜头边界（世界范围），保证不出现屏幕外空白
        if bounds is None:
            # 默认世界=一屏，bounds 就是整屏
            self.bounds = pygame.Rect(0, 0, settings.WIDTH, settings.HEIGHT)
        else:
            self.bounds = pygame.Rect(bounds)

        # 立即对齐到目标，避免开局镜头从 (0,0) 猛插值过去
        self.snap_to_target()

    # -------------------- 跟随 --------------------
    def set_target(self, target):
        """设置/切换跟随目标。"""
        self.target = target
        self.snap_to_target()

    def _desired_offset(self):
        """
        计算“理想偏移”：让目标中心落在屏幕中心时，镜头应处的偏移。
            目标中心(世界) - 屏幕中心 = 镜头应偏移量
        返回 (dx, dy)（未做边界限制）。
        """
        if self.target is None:
            return self.offset_x, self.offset_y

        # 目标中心（世界坐标）
        tx = getattr(self.target, "centerx", None)
        if tx is None:
            tx = self.target.x + getattr(self.target, "width", 0) / 2
        ty = self.target.y + getattr(self.target, "height", 0) / 2

        # 屏幕中心
        cx = settings.WIDTH / 2
        cy = settings.HEIGHT / 2

        return tx - cx, ty - cy

    def follow(self):
        """
        平滑跟随：
            offset += (desired - offset) * SMOOTH
        线性插值让镜头逐步靠近理想位置，产生柔软跟随。
        """
        dx, dy = self._desired_offset()

        # 线性插值（lerp）
        self.offset_x += (dx - self.offset_x) * self.SMOOTH
        self.offset_y += (dy - self.offset_y) * self.SMOOTH

        # 边界限制
        self._clamp_to_bounds()

    def snap_to_target(self):
        """立即对齐到目标（无插值），用于初始化或传送。"""
        dx, dy = self._desired_offset()
        self.offset_x = dx
        self.offset_y = dy
        self._clamp_to_bounds()

    def _clamp_to_bounds(self):
        """把 offset 限制在世界边界内，避免看到世界外。"""
        # 可移动范围 = 世界尺寸 - 屏幕尺寸
        max_x = self.bounds.width - settings.WIDTH
        max_y = self.bounds.height - settings.HEIGHT

        # 世界可能比屏幕小：此时锁定在 0 或居中
        if max_x <= 0:
            self.offset_x = 0.0
        else:
            self.offset_x = max(0.0, min(self.offset_x, self.bounds.left + max_x))

        if max_y <= 0:
            self.offset_y = 0.0
        else:
            self.offset_y = max(0.0, min(self.offset_y, self.bounds.top + max_y))

    # -------------------- 震动 --------------------
    def shake(self, intensity=5, duration=10):
        """
        触发震动。
        参数：
            intensity  震动强度（屏幕像素，随机偏移范围 ±intensity）
            duration   持续帧数
        多次调用取较强者，不会互相抵消。
        """
        self.shake_intensity = max(self.shake_intensity, float(intensity))
        self.shake_duration = max(self.shake_duration, int(duration))

    def _update_shake(self):
        """
        更新震动：
            若 duration > 0：
                - 生成本帧随机偏移（±intensity）
                - duration -= 1
                - intensity *= decay（逐帧减弱）
            否则偏移归零
        随机偏移无规律，观感更自然。
        """
        if self.shake_duration > 0:
            i = self.shake_intensity
            # 随机偏移（无规律）
            self._shake_offset_x = random.uniform(-i, i)
            self._shake_offset_y = random.uniform(-i, i)

            self.shake_duration -= 1
            self.shake_intensity *= self.shake_decay

            # 强度过低时直接归零，避免长时间极微震动
            if self.shake_intensity < 0.3:
                self.shake_intensity = 0.0
        else:
            self._shake_offset_x = 0.0
            self._shake_offset_y = 0.0
            self.shake_intensity = 0.0

    # -------------------- 更新 --------------------
    def update(self):
        """
        每帧更新：
            1. 先做平滑跟随（更新 offset）
            2. 再更新震动偏移（叠加在 offset 之上）
        """
        self.follow()
        self._update_shake()

    # -------------------- 坐标转换 --------------------
    def apply(self, surface_pos):
        """
        世界坐标 -> 屏幕坐标。
        参数：
            surface_pos  (x, y) 世界坐标
        返回：
            (x - offset_x + shake_x, y - offset_y + shake_y)
        """
        wx, wy = surface_pos
        return (
            wx - self.offset_x + self._shake_offset_x,
            wy - self.offset_y + self._shake_offset_y,
        )

    def apply_rect(self, world_rect):
        """
        世界 Rect -> 屏幕 Rect（保持尺寸不变，仅平移）。
        参数：
            world_rect  pygame.Rect（世界坐标）
        返回：
            pygame.Rect（屏幕坐标）
        """
        r = world_rect.copy()
        r.x = int(r.x - self.offset_x + self._shake_offset_x)
        r.y = int(r.y - self.offset_y + self._shake_offset_y)
        return r

    def apply_point_int(self, surface_pos):
        """世界坐标 -> 整数屏幕坐标（绘制用）。"""
        sx, sy = self.apply(surface_pos)
        return int(sx), int(sy)

    # -------------------- 可见区域 --------------------
    def get_rect(self):
        """
        返回当前镜头可见区域（世界坐标 Rect）。
        注意：不含震动偏移，表示“逻辑可见区域”。
        """
        return pygame.Rect(
            int(self.offset_x),
            int(self.offset_y),
            settings.WIDTH,
            settings.HEIGHT,
        )

    def get_render_offset(self):
        """
        返回渲染时应使用的总偏移（跟随 + 震动），供 main.py 整体平移画面。
        等价于 -offset + shake。
        """
        return (
            -self.offset_x + self._shake_offset_x,
            -self.offset_y + self._shake_offset_y,
        )

    # -------------------- 重置 --------------------
    def reset(self):
        """重置镜头（震动清零、对齐目标）。"""
        self.shake_intensity = 0.0
        self.shake_duration = 0
        self._shake_offset_x = 0.0
        self._shake_offset_y = 0.0
        self.snap_to_target()


# ============================================================
# 全局实例占位
# ============================================================
# 说明：main.py 中初始化 gameplay 后，用 camera = Camera(target=player, ...) 赋值。
# 本模块预先声明，方便其它模块 `import camera; camera.camera` 引用（可能为 None）。
camera = None


# ============================================================
# 桥接：把 particle.camera 的 shake 委托到本 Camera
# ============================================================
def bridge_global_camera(cam):
    """
    将本模块的全局 camera 注册到 particle.camera，让既有
    entity._shake_camera() / projectile._shake() 触发的震动
    也能作用于本 Camera。

    用法（main.py 初始化后调用）：
        import camera as camera_module
        cam = camera_module.Camera(target=player, bounds=world_rect)
        camera_module.camera = cam
        camera_module.bridge_global_camera(cam)

    参数：
        cam  Camera 实例
    """
    try:
        import particle as particle_module
        # particle.py 中的 camera 对象是简易版，提供 shake(magnitude, frames)
        # 这里把它替换为一个委托对象，转发到本 Camera
        class _CameraBridge:
            def __init__(self, target_cam):
                self._cam = target_cam
                self.offset = (0, 0)

            def shake(self, magnitude=3.0, frames=5):
                self._cam.shake(intensity=magnitude, duration=frames)
        particle_module.camera = _CameraBridge(cam)
    except Exception:
        # particle 模块缺失或结构不同，静默忽略
        pass


# ============================================================
# 简单测试
# ============================================================
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((settings.WIDTH, settings.HEIGHT))
    pygame.display.set_caption("Camera 测试 - 方向键移动 / 空格震动")
    clock = pygame.time.Clock()

    class Dummy:
        """测试目标：可被方向键移动。"""
        def __init__(self):
            self.x = 200
            self.y = 300
            self.width = 40
            self.height = 60

        @property
        def centerx(self):
            return self.x + self.width / 2

    world = pygame.Rect(0, 0, 1600, 1000)   # 虚拟大世界
    target = Dummy()
    cam = Camera(target=target, bounds=world)

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_SPACE:
                    cam.shake(8, 12)

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            target.x -= 5
        if keys[pygame.K_RIGHT]:
            target.x += 5
        if keys[pygame.K_UP]:
            target.y -= 5
        if keys[pygame.K_DOWN]:
            target.y += 5

        cam.update()

        screen.fill((30, 30, 40))
        # 画世界网格（世界坐标 -> 屏幕坐标）
        for gx in range(0, world.width, 100):
            x0, y0 = cam.apply((gx, 0))
            x1, y1 = cam.apply((gx, world.height))
            pygame.draw.line(screen, (50, 50, 60), (x0, y0), (x1, y1))
        for gy in range(0, world.height, 100):
            x0, y0 = cam.apply((0, gy))
            x1, y1 = cam.apply((world.width, gy))
            pygame.draw.line(screen, (50, 50, 60), (x0, y0), (x1, y1))

        # 画目标
        tx, ty = cam.apply((target.x, target.y))
        pygame.draw.rect(screen, (70, 130, 220),
                         (int(tx), int(ty), target.width, target.height))
        pygame.display.flip()
        clock.tick(settings.FPS)

    pygame.quit()