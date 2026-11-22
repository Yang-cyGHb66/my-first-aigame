"""
ui.py —《英雄大作战 - 原型》界面绘制

提供 UI 类：
    - draw_health_bar     通用属性条（带标签 + 数值 + 边框）
    - draw_player_ui      玩家三条主属性条
    - draw_enemy_ui       波次与敌人血条
    - draw_combo          连击数（缩放动画 + 变色）
    - draw_wave_announce  波次提示（滑入/停留/滑出）
    - draw_game_over      胜利/失败遮罩
    - draw_controls       操作说明
    - draw_fps            帧率显示

全局单例：ui = UI()

依赖：
    - pygame, settings

约定：
    所有方法均接收 surface 作为绘制目标；文字均带 2px 黑色阴影。
"""

import pygame

import settings


# ============================================================
# 工具：带阴影的文字绘制（模块级复用）
# ============================================================
def draw_text_shadow(surface, font, text, color, pos, center=False, shadow_offset=2):
    """
    绘制带阴影的文字。
    参数：
        surface       目标 surface
        font          pygame.font.Font
        text          文字内容
        color         主色
        pos           (x, y) 位置；center=True 时按中心对齐
        center        是否以 pos 为中心
        shadow_offset 阴影偏移像素（默认 2）
    返回：
        主文字 Rect（便于后续布局）
    """
    shadow_surf = font.render(text, True, settings.BLACK)
    main_surf = font.render(text, True, color)

    if center:
        main_rect = main_surf.get_rect(center=pos)
    else:
        main_rect = main_surf.get_rect(topleft=pos)

    # 先画阴影（右下偏移），再画主文字
    surface.blit(shadow_surf, (main_rect.x + shadow_offset, main_rect.y + shadow_offset))
    surface.blit(main_surf, main_rect.topleft)
    return main_rect


def lerp_color(c1, c2, t):
    """颜色线性插值（t 0~1）。"""
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


# ============================================================
# UI 类
# ============================================================
class UI:
    """游戏 UI 绘制集合。"""

    def __init__(self):
        # 统一字体族；逗号分隔可多字体回退
        family = "microsoftyahei,simhei,arial"
        self.font_small = pygame.font.SysFont(family, 14)
        self.font_medium = pygame.font.SysFont(family, 20)
        self.font_large = pygame.font.SysFont(family, 34, bold=True)
        self.font_huge = pygame.font.SysFont(family, 56, bold=True)

    # -------------------- 1. 通用属性条 --------------------
    def draw_health_bar(self, surface, x, y, width, height,
                        current, max_val, color, label=""):
        """
        绘制一条带标签的属性条。
        参数：
            surface  目标 surface
            x, y     左上角坐标
            width    条宽
            height   条高
            current  当前值
            max_val  最大值
            color    填充色
            label    左侧标签（如 "HP"）
        """
        # 比例裁剪
        ratio = 0.0
        if max_val > 0:
            ratio = max(0.0, min(1.0, current / max_val))

        bar_rect = pygame.Rect(x, y, width, height)

        # 底层：深灰背景
        pygame.draw.rect(surface, settings.DARK_GRAY, bar_rect)

        # 中层：当前值填充
        fill_w = int(width * ratio)
        if fill_w > 0:
            pygame.draw.rect(surface, color, (x, y, fill_w, height))

        # 上层：白色边框
        pygame.draw.rect(surface, settings.WHITE, bar_rect, 1)

        # 左侧标签
        if label:
            draw_text_shadow(surface, self.font_small, label,
                             settings.WHITE, (x + 4, y + (height - 14) // 2))

        # 右侧数值
        value_text = f"{int(current)}/{int(max_val)}"
        vsurf = self.font_small.render(value_text, True, settings.WHITE)
        vx = x + width - vsurf.get_width() - 4
        vy = y + (height - vsurf.get_height()) // 2
        draw_text_shadow(surface, self.font_small, value_text,
                         settings.WHITE, (vx, vy))

    # -------------------- 2. 玩家 UI --------------------
    def draw_player_ui(self, surface, player):
        """
        左上角绘制玩家三条大属性条。
        参数：
            surface 目标 surface
            player  玩家实体（需有 hp/mp/sp 及上限）
        """
        x = 14
        y = 14
        w = 200
        h = 18
        gap = 6

        self.draw_health_bar(surface, x, y, w, h,
                             player.hp, player.hp_max, settings.HP_RED, "HP")
        self.draw_health_bar(surface, x, y + h + gap, w, h,
                             player.mp, player.mp_max, settings.MP_BLUE, "MP")
        self.draw_health_bar(surface, x, y + (h + gap) * 2, w, h,
                             player.sp, player.sp_max, settings.SP_YELLOW, "SP")

    # -------------------- 3. 敌人 / 波次 UI --------------------
    def draw_enemy_ui(self, surface, enemy_manager):
        """
        右上角绘制波次信息 + 每个敌人的小血条。
        参数：
            surface        目标 surface
            enemy_manager  敌人管理器（需有 current_wave / total_waves / enemies）
        """
        wave = getattr(enemy_manager, "current_wave", 0) + 1
        total = getattr(enemy_manager, "total_waves", 1)
        enemies = getattr(enemy_manager, "enemies", [])

        alive = sum(1 for e in enemies if not getattr(e, "dead", False))

        text = f"第 {wave} 波   剩余：{alive}"
        ts = self.font_medium.render(text, True, settings.WHITE)
        tx = settings.WIDTH - ts.get_width() - 14
        ty = 14

        # 文本底衬（提高可读性）
        bg = pygame.Surface((ts.get_width() + 12, ts.get_height() + 6), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 90))
        surface.blit(bg, (tx - 6, ty - 3))

        draw_text_shadow(surface, self.font_medium, text, settings.WHITE, (tx, ty))

        # 每个敌人的小血条（横排于波次文字下方）
        small_w = 40
        small_h = 6
        gap = 6
        start_x = settings.WIDTH - 14 - (small_w + gap) * max(1, len(enemies)) + gap
        bar_y = ty + ts.get_height() + 10
        for i, enemy in enumerate(enemies):
            bx = start_x + i * (small_w + gap)
            ratio = 0.0
            hp_max = getattr(enemy, "hp_max", 1) or 1
            if not getattr(enemy, "dead", False):
                ratio = max(0.0, min(1.0, enemy.hp / hp_max))
            # 底槽
            pygame.draw.rect(surface, settings.DARK_GRAY, (bx, bar_y, small_w, small_h))
            if ratio > 0:
                pygame.draw.rect(surface, settings.HP_RED,
                                 (bx, bar_y, int(small_w * ratio), small_h))
            pygame.draw.rect(surface, settings.WHITE, (bx, bar_y, small_w, small_h), 1)

    # -------------------- 4. 连击数 --------------------
    def draw_combo(self, surface, combo_count, combo_timer):
        """
        屏幕中央偏上显示连击数，带缩放动画与变色。
        参数：
            surface      目标 surface
            combo_count  连击数（<=1 不显示）
            combo_timer  显示计时（用于估算出现时间，驱动缩放）
        """
        if combo_count <= 1:
            return

        # 字号随连击数增大：基础 30，每段 +5，上限 60
        font_size = min(60, 30 + (combo_count - 1) * 5)
        font = pygame.font.SysFont("microsoftyahei,simhei,arial", font_size, bold=True)

        # 颜色：1-2 白，3-5 黄，6+ 红
        if combo_count <= 2:
            color = settings.WHITE
        elif combo_count <= 5:
            color = settings.YELLOW
        else:
            color = settings.RED

        # 缩放动画：刚出现（timer 接近窗口上限）时 1.3 倍，逐渐回到 1.0
        # 用 combo_timer 相对 COMBO_WINDOW 的进度估出“年龄”
        window = max(1, settings.COMBO_WINDOW)
        # 计时越大说明越“新”，映射到缩放系数
        t = max(0.0, min(1.0, combo_timer / window))
        scale = 1.0 + 0.3 * t

        text = f"{combo_count} 连击！"
        base_surf = font.render(text, True, color)
        shadow_surf = font.render(text, True, settings.BLACK)

        # 按 scale 缩放
        if abs(scale - 1.0) > 0.01:
            w = int(base_surf.get_width() * scale)
            h = int(base_surf.get_height() * scale)
            base_surf = pygame.transform.smoothscale(base_surf, (w, h))
            shadow_surf = pygame.transform.smoothscale(shadow_surf, (w, h))

        cx = settings.WIDTH // 2
        cy = 130
        rect = base_surf.get_rect(center=(cx, cy))

        # 阴影 + 主文字
        surface.blit(shadow_surf, (rect.x + 3, rect.y + 3))
        surface.blit(base_surf, rect.topleft)

    # -------------------- 5. 波次提示 --------------------
    def draw_wave_announce(self, surface, wave_num, timer):
        """
        波次开始中央提示（滑入 -> 停留 60 帧 -> 滑出）。
        参数：
            surface   目标 surface
            wave_num  波次编号（从 1 开始）
            timer     剩余计时（总时长建议 >= 90，其中 60 帧停留）
        """
        if timer <= 0:
            return

        # 动画阶段划分（假设总时长 120 帧）
        total = 120
        timer = min(timer, total)
        elapsed = total - timer

        # 滑动进度：0-30 帧滑入，30-90 停留，90-120 滑出
        if elapsed < 30:
            slide_t = elapsed / 30.0
            x_offset = int((1.0 - slide_t) * -settings.WIDTH)
            alpha = int(255 * slide_t)
        elif elapsed < 90:
            x_offset = 0
            alpha = 255
        else:
            slide_t = (elapsed - 90) / 30.0
            x_offset = int(slide_t * settings.WIDTH)
            alpha = int(255 * (1.0 - slide_t))

        text = f"第 {wave_num} 波"
        base = self.font_huge.render(text, True, settings.YELLOW)
        shadow = self.font_huge.render(text, True, settings.BLACK)

        # 应用 alpha
        base.set_alpha(alpha)
        shadow.set_alpha(alpha)

        cx = settings.WIDTH // 2 + x_offset
        cy = settings.HEIGHT // 2 - 40
        rect = base.get_rect(center=(cx, cy))

        surface.blit(shadow, (rect.x + 4, rect.y + 4))
        surface.blit(base, rect.topleft)

    # -------------------- 6. 游戏结束 --------------------
    def draw_game_over(self, surface, result):
        """
        绘制游戏结束遮罩。
        参数：
            surface 目标 surface
            result  "VICTORY" 或 "DEFEAT"
        """
        # 半透明黑色遮罩 alpha=180
        overlay = pygame.Surface((settings.WIDTH, settings.HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        if result == "VICTORY":
            main_text = "胜  利"
            color = (255, 215, 0)      # 金色
        else:
            main_text = "失  败"
            color = settings.RED

        # 中央大字
        draw_text_shadow(surface, self.font_huge, main_text, color,
                         (settings.WIDTH // 2, settings.HEIGHT // 2 - 30),
                         center=True, shadow_offset=4)

        # 下方提示
        draw_text_shadow(surface, self.font_medium, "按 R 键重新开始",
                         settings.WHITE,
                         (settings.WIDTH // 2, settings.HEIGHT // 2 + 60),
                         center=True)

    # -------------------- 7. 操作说明 --------------------
    def draw_controls(self, surface):
        """
        左下角操作说明（小字，半透明）。
        参数：
            surface 目标 surface
        """
        lines = [
            "A/D 移动    W 跳跃    Shift 奔跑",
            "J 攻击    L 技能    S 防御    R 重开",
        ]
        line_h = self.font_small.get_height()
        padding = 6
        panel_w = 260
        panel_h = line_h * len(lines) + padding * 2
        panel_x = 10
        panel_y = settings.HEIGHT - panel_h - 10

        # 半透明底板：先画到临时 surface 再 blit
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 110))
        surface.blit(panel, (panel_x, panel_y))

        # 逐行绘制文字（含阴影）
        for i, line in enumerate(lines):
            ty = panel_y + padding + i * line_h
            draw_text_shadow(surface, self.font_small, line,
                             (220, 220, 220), (panel_x + padding, ty))

    # -------------------- 8. 帧率 --------------------
    def draw_fps(self, surface, fps):
        """
        右上角显示帧率（调试用）。
        参数：
            surface 目标 surface
            fps     当前帧率（float）
        """
        text = f"FPS: {int(fps)}"
        # 右上靠下一点，避免与波次文字重叠
        ts = self.font_small.render(text, True, settings.WHITE)
        x = settings.WIDTH - ts.get_width() - 14
        y = 60
        draw_text_shadow(surface, self.font_small, text, (180, 255, 180), (x, y))
