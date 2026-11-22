"""
main.py —《英雄大作战 - 原型》程序入口

职责（只做编排，不含游戏逻辑）：
    1. 初始化 Pygame 与实体
    2. 事件分发（事件缓存后共享给 Player，避免重复消费丢失）
    3. 主循环：输入 -> 更新 -> 碰撞/战斗判定 -> 渲染 -> 帧率控制
    4. HUD 与波次提示

模块依赖：
    settings  — 全局常量
    player    — 玩家角色（含输入、连招、技能）
    enemy     — 敌人 AI 与波次管理
    projectile— 弹体（可选，缺失时降级）
    particle  — 粒子（可选，缺失时降级）
"""

import pygame

import settings as s
import ui

pygame.init()

screen = pygame.display.set_mode((s.WIDTH, s.HEIGHT))
my_ui=ui.UI()

# ---- 可选模块：容错导入 ----
try:
    import projectile as projectile_module
except Exception:
    projectile_module = None

try:
    import particle as particle_module
except Exception:
    particle_module = None


# ============================================================
# 共享资源
# ============================================================
class Fonts:
    """集中管理字体，避免每帧 SysFont 创建开销。"""
    def __init__(self):
        # 兼容中文：优先黑体/雅黑，回退系统默认
        self.hud = pygame.font.SysFont("microsoftyahei,simhei,arial", 16)
        self.big = pygame.font.SysFont("microsoftyahei,simhei,arial", 34, bold=True)
        self.small = pygame.font.SysFont("microsoftyahei,simhei,arial", 13)


# ============================================================
# 战斗判定辅助
# ============================================================
def resolve_player_attack(player, enemies):
    """
    玩家攻击命中敌人：
        - 取玩家 get_hitbox()（仅判定阶段非 None）
        - 与每个存活敌人的 hurtbox 相交则造成伤害
        - 伤害：第三段用 DMG_COMBO3 并强制击退，其余用 DMG_NORMAL
        - 命中后短暂冷却，避免同一判定框连续多帧重复扣血
    """
    hitbox = player.get_hitbox()
    if hitbox is None:
        return

    # 每帧只对每个敌人结算一次（用本帧命中集合）
    for enemy in enemies:
        if enemy.dead:
            continue
        # 无敌帧 / 已死亡跳过由 take_damage 内部处理
        if hitbox.colliderect(enemy.hurtbox):
            is_finisher = player.combo_count >= 3
            dmg = s.DMG_COMBO3 if is_finisher else s.DMG_NORMAL
            enemy.take_damage(dmg, attacker=player, knockback=True)
            # 命中后立刻清空 hitbox，避免同一次攻击重复结算
            player.hitbox = None
            break   # 一次判定命中一个敌人即可（如需横扫可去掉 break）


def resolve_enemy_attacks(enemies, player):
    """
    敌人攻击命中玩家：
        - 每个敌人 get_hitbox() 与玩家 hurtbox 相交则扣 DMG_NORMAL
        - 命中后清空该敌人 hitbox，避免重复结算
    """
    if player.invincible_timer > 0 or player.dead:
        return
    for enemy in enemies:
        if enemy.dead:
            continue
        hb = enemy.get_hitbox()
        if hb is None:
            continue
        if hb.colliderect(player.hurtbox):
            player.take_damage(s.DMG_NORMAL, attacker=enemy, knockback=True)
            enemy.hitbox = None
            break


def resolve_projectiles(enemies, player):
    """
    更新弹体并处理与敌人的碰撞。
    依赖 projectile 模块提供 PROJECTILES 列表与弹体接口：
        proj.update()
        proj.draw(surface)
        proj.alive  (bool)
        proj.rect   (可选，没有则用 x/y + 尺寸)
        proj.damage
        proj.owner
    """
    if projectile_module is None:
        return
    projectiles = getattr(projectile_module, "PROJECTILES", None)
    if not isinstance(projectiles, list):
        return

    for p in list(projectiles):
        # 更新
        if hasattr(p, "update"):
            p.update()

        # 命中敌人（弹体属于玩家时）
        owner = getattr(p, "owner", None)
        if owner is player and not owner is None:
            p_rect = _proj_rect(p)
            if p_rect is not None:
                for enemy in enemies:
                    if enemy.dead:
                        continue
                    if p_rect.colliderect(enemy.hurtbox):
                        enemy.take_damage(getattr(p, "damage", s.DMG_SKILL),
                                          attacker=player, knockback=True)
                        _kill_projectile(p, projectiles)
                        break

        # 出屏移除
        if not getattr(p, "alive", True):
            _kill_projectile(p, projectiles)
            continue
        px = getattr(p, "x", 0)
        if px < -60 or px > s.WIDTH + 60:
            _kill_projectile(p, projectiles)


def _proj_rect(p):
    """尽量获取弹体矩形（优先 rect 属性，其次 x/y/w/h）。"""
    rect = getattr(p, "rect", None)
    if isinstance(rect, pygame.Rect):
        return rect
    x = getattr(p, "x", None)
    y = getattr(p, "y", None)
    if x is None or y is None:
        return None
    w = getattr(p, "width", 10)
    h = getattr(p, "height", 10)
    return pygame.Rect(int(x - w / 2), int(y - h / 2), w, h)


def _kill_projectile(p, projectiles):
    """从弹体列表中移除并标记死亡。"""
    try:
        if hasattr(p, "alive"):
            p.alive = False
    except Exception:
        pass
    if p in projectiles:
        projectiles.remove(p)


def update_particles():
    """驱动粒子模块（若提供 update_all）。"""
    if particle_module is not None and hasattr(particle_module, "update_all"):
        try:
            particle_module.update_all()
        except Exception:
            pass


def draw_particles(surface):
    """绘制粒子（若提供 draw_all）。"""
    if particle_module is not None and hasattr(particle_module, "draw_all"):
        try:
            particle_module.draw_all(surface)
        except Exception:
            pass


def draw_projectiles(surface):
    """绘制弹体。"""
    if projectile_module is None:
        return
    projectiles = getattr(projectile_module, "PROJECTILES", None)
    if not isinstance(projectiles, list):
        return
    for p in list(projectiles):
        if hasattr(p, "draw"):
            try:
                p.draw(surface)
            except Exception:
                pass


# ============================================================
# HUD 绘制
# ============================================================
def draw_hud(surface, fonts, player, manager, wave_text_timer):
    """
    HUD：
        - 左上：HP/MP/SP 数值
        - 右上：波次与剩余敌人
        - 中上：波次切换提示（wave_text_timer > 0 时显示）
        - 底部：操作提示
    """
    # 左上属性
    surface.blit(fonts.hud.render(f"HP {int(player.hp)}/{player.hp_max}", True, s.HP_RED), (10, 8))
    surface.blit(fonts.hud.render(f"MP {int(player.mp)}/{player.mp_max}", True, s.MP_BLUE), (10, 28))
    surface.blit(fonts.hud.render(f"SP {int(player.sp)}/{player.sp_max}", True, s.SP_YELLOW), (10, 48))

    # 右上波次
    wave_label = f"波次 {manager.current_wave + 1}/{manager.total_waves}"
    alive = manager.alive_count()
    wave_surf = fonts.hud.render(f"{wave_label}   敌人 {alive}", True, s.WHITE)
    wave_bg = pygame.Surface((wave_surf.get_width() + 12, wave_surf.get_height() + 6), pygame.SRCALPHA)
    wave_bg.fill((0, 0, 0, 100))
    tx = s.WIDTH - wave_surf.get_width() - 18
    surface.blit(wave_bg, (tx - 6, 6))
    surface.blit(wave_surf, (tx, 9))

    # 中上波次切换提示
    if wave_text_timer > 0:
        text = "第 {} 波".format(manager.current_wave + 1)
        big = fonts.big.render(text, True, s.YELLOW)
        # 随时间淡出
        alpha = min(255, int(255 * (wave_text_timer / 90)))
        tmp = big.copy()
        tmp.set_alpha(alpha)
        rect = tmp.get_rect(center=(s.WIDTH // 2, 90))
        surface.blit(tmp, rect)

    # 底部操作提示
    tip = fonts.small.render(
        "A/D 移动  Shift 奔跑  W 跳跃  J 攻击  K 空中攻击  L 技能  S 防御  R 复活  F1 调试",
        True, s.WHITE,
    )
    tip_bg = pygame.Surface((tip.get_width() + 8, tip.get_height() + 6), pygame.SRCALPHA)
    tip_bg.fill((0, 0, 0, 90))
    surface.blit(tip_bg, (6, s.HEIGHT - tip_bg.get_height() - 4))
    surface.blit(tip, (10, s.HEIGHT - tip.get_height() - 6))


def draw_death_overlay(surface, fonts, player):
    """玩家死亡提示。"""
    if not player.dead:
        return
    overlay = pygame.Surface((s.WIDTH, s.HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 120))
    surface.blit(overlay, (0, 0))
    msg = fonts.big.render("你被击倒了！按 R 复活", True, s.RED)
    rect = msg.get_rect(center=(s.WIDTH // 2, s.HEIGHT // 2))
    surface.blit(msg, rect)


def draw_victory_overlay(surface, fonts):
    """通关提示。"""
    overlay = pygame.Surface((s.WIDTH, s.HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 150))
    surface.blit(overlay, (0, 0))
    msg = fonts.big.render("全部波次清除！胜利！", True, s.YELLOW)
    rect = msg.get_rect(center=(s.WIDTH // 2, s.HEIGHT // 2 - 10))
    surface.blit(msg, rect)
    sub = fonts.hud.render("按 ESC 退出", True, s.WHITE)
    surface.blit(sub, sub.get_rect(center=(s.WIDTH // 2, s.HEIGHT // 2 + 40)))


# ============================================================
# 主函数
# ============================================================
def main():
    # ---------- 初始化 ----------
    pygame.init()
    screen = pygame.display.set_mode((s.WIDTH, s.HEIGHT))
    pygame.display.set_caption(s.TITLE)
    clock = pygame.time.Clock()
    fonts = Fonts()

    # 延迟导入实体，确保 pygame 已初始化
    from player import Player
    from enemy import EnemyManager

    player = Player(x=120, y=s.GROUND_Y - 96)
    manager = EnemyManager()

    # 状态标志
    show_debug = False
    wave_text_timer = 60      # 初始显示“第 1 波”
    victory = False           # 是否已通关

    running = True

    # ---------- 主循环 ----------
    while running:
        # 1. 事件处理（缓存后共享给 Player，避免事件被提前消费）
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_F1:
                    show_debug = not show_debug
                elif event.key == pygame.K_r and player.dead:
                    player.respawn()

        # Player 内部需要用事件做 R / ESC 判定，这里把缓存事件塞给它
        # （player.handle_input 会在 update 中调用，见下方兼容处理）
        player._cached_events = events

        # 2. 逻辑更新
        player.update()
        manager.update(player)

        # 3. 战斗判定
        resolve_player_attack(player, manager.enemies)
        resolve_enemy_attacks(manager.enemies, player)
        resolve_projectiles(manager.enemies, player)
        update_particles()

        # 4. 波次推进
        if not victory:
            if manager.all_dead():
                if manager.is_last_wave():
                    # 最后一波清光 -> 通关
                    victory = True
                else:
                    if manager.next_wave():
                        wave_text_timer = 90

        # 波次提示淡出
        if wave_text_timer > 0:
            wave_text_timer -= 1

        # 5. 渲染 —— 背景
        screen.fill(s.SKY_BLUE)
        # 远景色块装饰（云或山，简化为两个浅色块）
        pygame.draw.ellipse(screen, (200, 230, 250), (60, 70, 180, 50))
        pygame.draw.ellipse(screen, (210, 235, 250), (560, 120, 160, 40))
        # 草地条
        pygame.draw.rect(screen, s.GRASS_GREEN, (0, s.GROUND_Y - 8, s.WIDTH, 8))
        # 地面
        ground = pygame.Rect(0, s.GROUND_Y, s.WIDTH, s.HEIGHT - s.GROUND_Y)
        pygame.draw.rect(screen, s.GROUND_BROWN, ground)
        pygame.draw.line(screen, s.BLACK, (0, s.GROUND_Y), (s.WIDTH, s.GROUND_Y), 2)

        # 6. 渲染 —— 实体与效果
        manager.draw(screen)
        player.draw(screen)
        draw_projectiles(screen)
        draw_particles(screen)

        # 7. 调试框
        if show_debug:
            player.draw_debug(screen)
            for enemy in manager.enemies:
                enemy.draw_debug(screen)

        # 8. HUD 与覆盖层
        draw_hud(screen, fonts, player, manager, wave_text_timer)
        draw_death_overlay(screen, fonts, player)
        if victory:
            draw_victory_overlay(screen, fonts)

        pygame.display.flip()

        # 9. 帧率控制
        clock.tick(s.FPS)

    pygame.quit()


if __name__ == "__main__":
    main()