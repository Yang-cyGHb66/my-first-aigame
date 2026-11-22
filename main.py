"""
main.py —《英雄大作战 - 原型》程序入口
负责：初始化、主循环、事件分发、渲染调度
"""

import os
import pygame
import settings as s   # 用别名 s，调用时写 s.WIDTH，简洁且不冲突


class Player:
    """玩家角色：矩形占位，后续替换为精灵图"""

    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 40, 60)   # 宽40 高60 的占位方块
        self.vx = 0.0        # 水平速度
        self.vy = 0.0        # 垂直速度
        self.on_ground = False
        self.facing = 1      # 1 朝右，-1 朝左

    def update(self, keys):
        # ---------- 水平输入 ----------
        move = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move = -1
        elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move = 1

        if move != 0:
            self.vx = move * s.PLAYER_SPEED
            self.facing = move
        else:
            # 地面摩擦衰减，空中保留惯性
            self.vx *= s.FRICTION if self.on_ground else 1.0
            if abs(self.vx) < 0.1:
                self.vx = 0

        # ---------- 跳跃 ----------
        if (keys[pygame.K_w] or keys[pygame.K_SPACE]) and self.on_ground:
            self.vy = s.JUMP_VELOCITY
            self.on_ground = False

        # ---------- 重力 ----------
        self.vy += s.GRAVITY

        # ---------- 位移 ----------
        self.rect.x += int(self.vx)
        self.rect.y += int(self.vy)

        # ---------- 地面碰撞 ----------
        if self.rect.bottom >= s.GROUND_Y:
            self.rect.bottom = s.GROUND_Y
            self.vy = 0
            self.on_ground = True

        # ---------- 屏幕边界 ----------
        if self.rect.left < 0:
            self.rect.left = 0
        if self.rect.right > s.WIDTH:
            self.rect.right = s.WIDTH

    def draw(self, surface):
        # 主体
        pygame.draw.rect(surface, s.PLAYER_BODY, self.rect)
        # 描边
        pygame.draw.rect(surface, s.PLAYER_DARK, self.rect, 2)
        # 朝向指示（一个小方块，看出面朝哪边）
        eye_x = self.rect.right - 12 if self.facing == 1 else self.rect.left + 4
        eye = pygame.Rect(eye_x, self.rect.top + 12, 8, 8)
        pygame.draw.rect(surface, s.WHITE, eye)


def main():
    # ---------- 初始化 ----------
    pygame.init()
    screen = pygame.display.set_mode((s.WIDTH, s.HEIGHT))
    pygame.display.set_caption(s.TITLE)
    clock = pygame.time.Clock()

    player = Player(x=100, y=s.GROUND_Y - 60)

    running = True

    # ---------- 主循环 ----------
    while running:
        # 1. 事件处理
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # 2. 逻辑更新
        keys = pygame.key.get_pressed()
        player.update(keys)

        # 3. 渲染
        screen.fill(s.SKY_BLUE)                          # 天空
        ground = pygame.Rect(0, s.GROUND_Y, s.WIDTH, s.HEIGHT - s.GROUND_Y)
        pygame.draw.rect(screen, s.GROUND_BROWN, ground) # 地面
        pygame.draw.line(screen, s.BLACK, (0, s.GROUND_Y), (s.WIDTH, s.GROUND_Y), 2)

        player.draw(screen)

        pygame.display.flip()

        # 4. 帧率控制
        clock.tick(s.FPS)

    pygame.quit()


if __name__ == "__main__":
    main()