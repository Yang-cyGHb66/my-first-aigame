"""
main.py —《英雄大作战 - 原型》主入口

结构：
    Game 类封装整个游戏生命周期：
        __init__ -> reset -> run(handle_events / update / draw 循环)
    模块导入全部置于顶部；运行时依赖通过延迟初始化解决循环引用。

镜头处理：
    entity/player/enemy/projectile 的 draw 直接画到 target surface，
    世界坐标即屏幕坐标（单屏世界）。为了让 camera 的震动/跟随对实体生效：
    做法是「平移画布」——绘制世界层时给所有实体套一层坐标偏移。
    由于既有 Entity.draw 不接收 offset 参数，本实现用「临时偏移注入」：
        camera_ctx 上下文：把实体的 x/y 临时减去 offset，绘制后复原。
    这样既不改动既有 draw 代码，又能让镜头偏移作用到全部实体。
"""

import sys
import random

import pygame

import settings
from player import Player
from enemy import EnemyManager
from projectile import ProjectileManager
from particle import effects
import particle
import camera as camera_module
from ui import ui


# ============================================================
# 临时坐标偏移（镜头平移适配）
# ============================================================
class _CameraOffsetCtx:
    """
    上下文管理器：进入时把实体的绘制坐标按镜头偏移平移，退出时复原。
    这样既有 Entity.draw（直接读 self.x/self.y）无需修改即可配合镜头。
    """
    def __init__(self, camera, entities):
        self.camera = camera
        self.entities = entities
        self.saved = []

    def __enter__(self):
        ox, oy = self.camera.get_render_offset()
        for e in self.entities:
            self.saved.append((e, e.x, e.y))
            e.x += ox
            e.y += oy
        return self

    def __exit__(self, exc_type, exc, tb):
        for e, sx, sy in self.saved:
            e.x = sx
            e.y = sy
        return False


# ============================================================
# Game 类
# ============================================================
class Game:
    """游戏主类：封装初始化、重置、事件、更新、绘制、主循环。"""

    # -------------------- 初始化 --------------------
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((settings.WIDTH, settings.HEIGHT))
        pygame.display.set_caption(settings.TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        # 实体与系统（在 reset 中创建）
        self.player = None
        self.enemy_manager = None
        self.projectile_manager = None
        self.camera = None

        # 游戏状态
        self.game_state = "playing"    # playing / victory / defeat
        self.wave_announce_timer = 0
        self.current_wave = 0

        self.reset()

    # -------------------- 重置 --------------------
    def reset(self):
        """
        重置所有游戏对象到初始状态。
        玩家位置 (100, GROUND_Y - 100)，敌人管理器生成第一波。
        """
        # 玩家：脚底贴地（entity 高 96，故 y = GROUND_Y - 96）
        self.player = Player(x=100, y=settings.GROUND_Y - 96)

        # 敌人管理器（内部自动生成第 0 波）
        self.enemy_manager = EnemyManager()

        # 弹道管理器
        self.projectile_manager = ProjectileManager()

        # 关键：把弹道管理器注入玩家，使技能弹体进入统一更新/碰撞/绘制流程
        self.player.projectile_manager = self.projectile_manager

        # 镜头：跟随玩家，单屏世界边界
        world_rect = pygame.Rect(0, 0, settings.WIDTH, settings.HEIGHT)
        self.camera = camera_module.Camera(target=self.player, bounds=world_rect)
        # 注册为全局 camera（兼容其它模块引用）
        camera_module.camera = self.camera
                # 桥接 particle 的 shake 到本 Camera（使 entity/projectile 的震动生效）
        camera_module.bridge_global_camera(self.camera)

        # 重置状态
        self.game_state = "playing"
        self.current_wave = 0
        # 注意：EnemyManager 构造时已生成第 0 波，这里不再重复 spawn_wave(0)
        self.current_wave = self.enemy_manager.current_wave
        self.wave_announce_timer = 90

    # -------------------- 事件 --------------------
    def handle_events(self):
        """
        事件处理：
            QUIT / ESC -> 退出
            R（非 playing 状态）-> 重开
        事件列表缓存后额外交给 player（Player.handle_input 内部已能读队列，
        但为避免双重消费导致 R 复活失效，主循环也兜底处理 R）。
        """
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    # 结算后重开
                    if self.game_state != "playing":
                        self.reset()
                    # playing 状态下按 R 由 Player 内部处理（玩家死亡复活）

        # 把缓存事件交给 Player（可选钩子）
        try:
            self.player._cached_events = events
        except Exception:
            pass

    # -------------------- 更新 --------------------
    def update(self):
        """逻辑更新：实体 -> 弹道 -> 粒子 -> 镜头 -> 状态检查。"""
        if self.game_state == "playing":
            # 1. 玩家
            self.player.update()

                        # 2. 敌人
            self.enemy_manager.update(self.player)

            # 3. 弹道：更新 + 碰撞检测（目标含玩家和所有敌人，owner 会自动跳过）
            targets = [self.player] + self.enemy_manager.enemies
            self.projectile_manager.update(targets)
            self.projectile_manager.clear()

            # 4. 粒子（模块级 update_all 推进粒子）
            particle.update_all()

            # 5. 镜头（update 内部已包含 follow 平滑跟随 + 震动更新）
            self.camera.update()

            # 6. 状态检查：玩家死亡 -> 失败
            if self.player.hp <= 0 and self.game_state == "playing":
                self.game_state = "defeat"

            # 7. 状态检查：敌人全灭 -> 下一波 或 胜利
            elif self.game_state == "playing" and self.enemy_manager.all_dead():
                if self.enemy_manager.is_last_wave():
                    self.game_state = "victory"
                else:
                    if self.enemy_manager.next_wave():
                        self.current_wave = self.enemy_manager.current_wave
                        self.wave_announce_timer = 90

        # 波次公告计时递减
        if self.wave_announce_timer > 0:
            self.wave_announce_timer -= 1

    # -------------------- 绘制 --------------------
    def draw(self):
        """渲染：背景 -> 实体（含镜头偏移）-> 粒子 -> UI -> 结算。"""
        # 1. 背景（视差）
        self.draw_background()

        # 2. 世界层实体（镜头偏移对实体位置生效）
        world_entities = list(self.enemy_manager.enemies) + [self.player]

        with _CameraOffsetCtx(self.camera, world_entities):
            # 敌人
            for enemy in self.enemy_manager.enemies:
                enemy.draw(self.screen)
            # 玩家
            self.player.draw(self.screen)

        # 3. 弹道（弹体自带绘制，坐标也需镜头偏移）
        with _CameraOffsetCtx(self.camera, self.projectile_manager.projectiles):
            self.projectile_manager.draw(self.screen)

        # 4. 粒子（粒子位置是世界坐标，也需偏移；但粒子由 particle 模块绘制，
        #    这里直接对粒子列表做偏移上下文）
        with _CameraOffsetCtx(self.camera, effects.particles):
            effects.draw(self.screen)

        # 5. UI（屏幕层，不跟随镜头）
        self.draw_ui()

        # 6. 结算遮罩
        if self.game_state == "victory":
            ui.draw_game_over(self.screen, "VICTORY")
        elif self.game_state == "defeat":
            ui.draw_game_over(self.screen, "DEFEAT")

        pygame.display.flip()

    # -------------------- 背景 --------------------
    def draw_background(self):
        """
        三层背景：
            天空（SKY_BLUE）+ 远山（深绿三角，半透明，视差 0.3x）+ 地面（GRASS_GREEN）
        视差：远山的绘制位置按 camera.offset_x * 0.3 偏移。
        """
        # ---- 1. 天空 ----
        sky_rect = pygame.Rect(0, 0, settings.WIDTH, settings.GROUND_Y)
        self.screen.fill(settings.SKY_BLUE, sky_rect)

        # 天空顶部渐变（浅 -> SKY_BLUE），简易两段色增加层次
        top = pygame.Surface((settings.WIDTH, 80), pygame.SRCALPHA)
        for i in range(80):
            alpha = int(60 * (1 - i / 80))
            pygame.draw.line(top, (255, 255, 255, alpha), (0, i), (settings.WIDTH, i))
        self.screen.blit(top, (0, 0))

        # ---- 2. 远山（视差 0.3） ----
        parallax_x = self.camera.offset_x * 0.3
        mountains = [
            # (中心x, 山顶y, 山底宽)
            (-100, settings.GROUND_Y - 260, 420),
            (240, settings.GROUND_Y - 220, 360),
            (560, settings.GROUND_Y - 280, 460),
            (880, settings.GROUND_Y - 200, 340),
        ]
        mountain_surf = pygame.Surface((settings.WIDTH, settings.GROUND_Y), pygame.SRCALPHA)
        for mcx, my, mw in mountains:
            sx = mcx - parallax_x
            # 只画视野内的山
            if sx > settings.WIDTH + mw or sx < -mw:
                continue
            base_y = settings.GROUND_Y
            pts = [
                (int(sx), int(my)),
                (int(sx - mw / 2), base_y),
                (int(sx + mw / 2), base_y),
            ]
            # 半透明深绿（alpha=160）
            pygame.draw.polygon(mountain_surf, (60, 140, 70, 160), pts)
            # 山体暗边
            pygame.draw.polygon(mountain_surf, (40, 105, 55, 210), pts, 2)
        self.screen.blit(mountain_surf, (0, 0))

        # ---- 3. 地面 ----
        ground_rect = pygame.Rect(0, settings.GROUND_Y, settings.WIDTH, settings.HEIGHT - settings.GROUND_Y)
        pygame.draw.rect(self.screen, settings.GRASS_GREEN, ground_rect)

        # 地面线（4px 厚棕色）
        pygame.draw.line(self.screen, settings.GROUND_BROWN,
                         (0, settings.GROUND_Y),
                         (settings.WIDTH, settings.GROUND_Y), 4)

        # 地面纹理：视差草簇（0.5x）
        grass_surf = pygame.Surface((settings.WIDTH, settings.HEIGHT - settings.GROUND_Y), pygame.SRCALPHA)
        grass_parallax = self.camera.offset_x * 0.5
        for gx in range(-1, settings.WIDTH // 40 + 3):
            px = int(gx * 40 - (grass_parallax % 40))
            pygame.draw.line(grass_surf, (80, 140, 60, 220),
                             (px, settings.GROUND_Y - settings.GROUND_Y),
                             (px + 4, settings.GROUND_Y - settings.GROUND_Y - 12), 2)
        self.screen.blit(grass_surf, (0, settings.GROUND_Y - 12))

    # -------------------- UI --------------------
    def draw_ui(self):
        """绘制所有 UI 元素（屏幕坐标，不随镜头移动）。"""
        # 玩家属性条
        ui.draw_player_ui(self.screen, self.player)

        # 敌人/波次
        ui.draw_enemy_ui(self.screen, self.enemy_manager)

        # 连击数（用 combo_display 展示残留，而非 combo_count 瞬时值）
        ui.draw_combo(self.screen, self.player.combo_display, self.player.combo_display_timer)

        # 波次公告
        if self.wave_announce_timer > 0:
            ui.draw_wave_announce(self.screen,
                                  self.enemy_manager.current_wave + 1,
                                  self.wave_announce_timer)

        # 操作说明
        ui.draw_controls(self.screen)

        # FPS（调试）
        ui.draw_fps(self.screen, self.clock.get_fps())

    # -------------------- 主循环 --------------------
    def run(self):
        """游戏主循环：事件 -> 更新 -> 绘制 -> 帧率控制。"""
        while self.running:
            # 1. 事件处理
            self.handle_events()
            # 2. 逻辑更新
            self.update()
            # 3. 渲染
            self.draw()
            # 4. 帧率控制
            self.clock.tick(settings.FPS)

        # 退出清理
        pygame.quit()
        sys.exit()


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    game = Game()
    game.run()