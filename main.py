"""
main.py —《英雄大作战 - 原型》程序入口
负责：初始化、主循环、事件分发、渲染调度

说明：
    - Player / Enemy 等实体逻辑已拆分到独立模块
    - 本文件只做“编排”：初始化 -> 事件 -> 更新 -> 绘制 -> 帧率控制
    - 实体内部已自行读取键盘输入与自身状态机，主循环无需再传 keys
"""

import pygame

import settings as s        # 用别名 s，调用时写 s.WIDTH，简洁且不冲突


# ============================================================
# 主函数
# ============================================================
def main():
    # ---------- 初始化 ----------
    pygame.init()
    screen = pygame.display.set_mode((s.WIDTH, s.HEIGHT))
    pygame.display.set_caption(s.TITLE)
    clock = pygame.time.Clock()

    # 延迟导入：确保 pygame 已初始化，同时避免循环引用
    from player import Player

    # 玩家初始位置：脚底贴地（实体高 96，故 y = 地面 - 高度）
    player = Player(x=100, y=s.GROUND_Y - 96)

    # 调试开关（F1 切换，或按住显示受击框/攻击框）
    show_debug = False

    running = True

    # ---------- 主循环 ----------
    while running:
        # 1. 事件处理（系统级）
        #    注意：Player.handle_input() 内部也会消费 pygame.event.get()，
        #    但 Pygame 的事件队列是全局的，重复获取不会丢失，
        #    只是会“读走”后续帧拿不到的按键事件；因此这里只处理 QUIT。
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                # ESC 退出（Player 内部也会 post QUIT，这里双保险）
                if event.key == pygame.K_ESCAPE:
                    running = False
                # F1 切换调试显示
                elif event.key == pygame.K_F1:
                    show_debug = not show_debug

        # 2. 逻辑更新（实体内部自行读取输入并驱动状态机）
        player.update()

        # 3. 渲染
        # ---- 背景：天空 ----
        screen.fill(s.SKY_BLUE)

        # ---- 远景草地条（装饰） ----
        grass = pygame.Rect(0, s.GROUND_Y - 8, s.WIDTH, 8)
        pygame.draw.rect(screen, s.GRASS_GREEN, grass)

        # ---- 地面 ----
        ground = pygame.Rect(0, s.GROUND_Y, s.WIDTH, s.HEIGHT - s.GROUND_Y)
        pygame.draw.rect(screen, s.GROUND_BROWN, ground)
        pygame.draw.line(screen, s.BLACK, (0, s.GROUND_Y), (s.WIDTH, s.GROUND_Y), 2)

        # ---- 实体绘制 ----
        player.draw(screen)

        # ---- 调试框 ----
        if show_debug:
            player.draw_debug(screen)

        # ---- HUD（画布左上角大字提示，简易绘制，不依赖字体文件） ----
        _draw_hud(screen, player)

        pygame.display.flip()

        # 4. 帧率控制
        clock.tick(s.FPS)

    pygame.quit()


# ============================================================
# HUD 辅助：使用 Pygame 系统字体显示关键信息
# ============================================================
def _draw_hud(surface, player):
    """
    简易 HUD：
        - 左上角显示 HP/MP/SP 数值
        - 右下角显示操作提示
    使用 pygame.font.SysFont（不需要 extra 字体文件）。
    """
    font = pygame.font.SysFont("simhei", 16)   # 中文友好字体，回退时会自动降级
    small = pygame.font.SysFont("simhei", 12)

    text_hp = font.render(f"HP {int(player.hp)}/{player.hp_max}", True, s.HP_RED)
    text_mp = font.render(f"MP {int(player.mp)}/{player.mp_max}", True, s.MP_BLUE)
    text_sp = font.render(f"SP {int(player.sp)}/{player.sp_max}", True, s.SP_YELLOW)

    surface.blit(text_hp, (10, 10))
    surface.blit(text_mp, (10, 30))
    surface.blit(text_sp, (10, 50))

    tip = small.render(
        "A/D 移动  Shift 奔跑  W 跳跃  J 攻击  K 空中攻击  L 技能  S 防御  F1 调试",
        True, s.WHITE,
    )
    # 半透明底条提升可读性
    tip_bg = pygame.Surface((tip.get_width() + 8, tip.get_height() + 4), pygame.SRCALPHA)
    tip_bg.fill((0, 0, 0, 90))
    surface.blit(tip_bg, (6, s.HEIGHT - tip_bg.get_height() - 6))
    surface.blit(tip, (10, s.HEIGHT - tip.get_height() - 8))


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    main()