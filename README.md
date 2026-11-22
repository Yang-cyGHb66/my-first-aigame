# my-first-aigame
A small game built with Python and Pygame

# 附加说明

该游戏是本人采用VScode与DeepSeek智能体制作（代码由智能体生成并修改），原型参照比较老的一款游戏《英雄大作战》，制作目的仅为体验智能体辅助开发流程，且目前仅有简单原型，并无侵权之意。后续更改也只作娱乐目的，不存在其他倾向或目的。

# 英雄大作战 - 横版动作游戏原型

基于 Python + Pygame 开发的横版动作游戏原型。

## 运行方式

1. 安装 Python 3.10+
2. 安装依赖：pip install pygame
3. 运行：python main.py

## 操作说明

- A/D 或 ←/→：移动
- W 或 ↑：跳跃
- J：攻击
- K：技能
- 空格：闪避

## 项目结构

- settings.py：全局常量配置
- states.py：状态机
- entity.py：实体基类
- player.py：玩家角色
- enemy.py：敌人 AI
- projectile.py：投射物系统
- particle.py：粒子特效
- camera.py：镜头跟随
- ui.py：界面绘制
- main.py：主程序入口
