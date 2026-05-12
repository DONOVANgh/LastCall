
import math
import re
import sys
import tempfile
from pathlib import Path

import pygame


pygame.init()

BASE_WIDTH = 1280
BASE_HEIGHT = 720
SHOP_WIDTH = 260
FPS = 60
SPAWN_INTERVAL_MS = 1600
STARTING_MONEY = 125
STARTING_LIVES = 10
PATH_WIDTH = 42

ART_FILE = Path(__file__).with_name("art.html")

SCREEN = pygame.display.set_mode((BASE_WIDTH, BASE_HEIGHT))
pygame.display.set_caption("Alien Track Defense")
CLOCK = pygame.time.Clock()
FONT = pygame.font.SysFont("consolas", 24)
SMALL_FONT = pygame.font.SysFont("consolas", 18)

TOWER_TYPES = {
    "basic": {"cost": 25, "range": 145, "fire_rate": 0.80, "damage": 1.0, "color": (60, 90, 170)},
    "sniper": {"cost": 60, "range": 275, "fire_rate": 1.75, "damage": 3.0, "color": (150, 60, 180)},
    "rapid": {"cost": 40, "range": 105, "fire_rate": 0.25, "damage": 0.5, "color": (200, 140, 60)},
}

BASE_PATH_POINTS = [
    (20, 35), (70, 80), (70, 250), (220, 250), (240, 90), (340, 40),
    (480, 40), (530, 80), (530, 300), (620, 300), (620, 155),
    (740, 155), (760, 180), (760, 455), (610, 455), (480, 445),
    (110, 445), (75, 500), (20, 540),
]


def build_buttons():
    buttons = {}
    y = 90
    for name in TOWER_TYPES:
        buttons[name] = pygame.Rect(BASE_WIDTH - SHOP_WIDTH + 20, y, SHOP_WIDTH - 40, 74)
        y += 96
    return buttons


def scale_path(points):
    game_width = BASE_WIDTH - SHOP_WIDTH
    x_scale = game_width / 800
    y_scale = BASE_HEIGHT / 560
    return [(int(x * x_scale), int(y * y_scale)) for x, y in points]


PATH_POINTS = scale_path(BASE_PATH_POINTS)
BUTTONS = build_buttons()


def point_segment_distance(point, start, end):
    px, py = point
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    if dx == 0 and dy == 0:
        return math.hypot(px - sx, py - sy)
    t = ((px - sx) * dx + (py - sy) * dy) / float(dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nearest_x = sx + t * dx
    nearest_y = sy + t * dy
    return math.hypot(px - nearest_x, py - nearest_y)


def point_on_path(point, margin=28):
    for start, end in zip(PATH_POINTS, PATH_POINTS[1:]):
        if point_segment_distance(point, start, end) <= (PATH_WIDTH / 2) + margin:
            return True
    return False


def extract_svg_assets(html_path):
    html = html_path.read_text(encoding="utf-8")
    style_match = re.search(r"<style>(.*?)</style>", html, re.DOTALL | re.IGNORECASE)
    style_block = style_match.group(1) if style_match else ""

    svgs = {}
    matches = re.findall(
        r'(<svg[^>]*data-art="([^"]+)"[^>]*>.*?</svg>)',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    for full_svg, art_id in matches:
        if "<style>" not in full_svg:
            full_svg = full_svg.replace(">", f"><style>{style_block}</style>", 1)
        svgs[art_id] = full_svg
    return svgs


def load_svg_surface(svg_markup, size, fallback_color):
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as handle:
        handle.write(svg_markup)
        temp_path = handle.name

    try:
        surface = pygame.image.load(temp_path).convert_alpha()
        return pygame.transform.smoothscale(surface, size)
    except Exception:
        fallback = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.ellipse(fallback, fallback_color, fallback.get_rect())
        pygame.draw.ellipse(fallback, (20, 20, 20), fallback.get_rect(), 3)
        return fallback
    finally:
        Path(temp_path).unlink(missing_ok=True)


def load_art_surfaces():
    default = {
        "alien": load_svg_surface('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 160"></svg>', (52, 70), (76, 196, 76)),
        "ufo": load_svg_surface('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 120"></svg>', (96, 44), (150, 160, 220)),
    }

    if not ART_FILE.exists():
        return default

    svgs = extract_svg_assets(ART_FILE)
    if "alien" in svgs:
        default["alien"] = load_svg_surface(svgs["alien"], (52, 70), (76, 196, 76))
    if "ufo" in svgs:
        default["ufo"] = load_svg_surface(svgs["ufo"], (96, 44), (150, 160, 220))
    return default


ART_SURFACES = load_art_surfaces()


class Enemy:
    def __init__(self, skin_name):
        self.skin_name = skin_name
        self.sprite = ART_SURFACES[skin_name]
        self.pos = pygame.Vector2(PATH_POINTS[0])
        self.index = 1
        self.speed = 105 if skin_name == "alien" else 135
        self.hp = 4 if skin_name == "alien" else 3
        self.max_hp = self.hp
        self.alive = True
        self.reached = False
        self.reward = 10
        self.direction = pygame.Vector2(1, 0)

    @property
    def radius(self):
        return max(self.sprite.get_width(), self.sprite.get_height()) // 3

    def update(self, dt):
        if not self.alive:
            return False

        if self.index >= len(PATH_POINTS):
            self.reached = True
            return False

        target = pygame.Vector2(PATH_POINTS[self.index])
        direction = target - self.pos

        if direction.length_squared() == 0:
            self.index += 1
            return True

        self.direction = direction.normalize()
        step = self.speed * dt
        if step >= direction.length():
            self.pos = target
            self.index += 1
        else:
            self.pos += self.direction * step
        return True

    def draw(self, surface):
        angle = -math.degrees(math.atan2(self.direction.y, self.direction.x))
        sprite = pygame.transform.rotate(self.sprite, angle * 0.15 if self.skin_name == "ufo" else 0)
        rect = sprite.get_rect(center=(self.pos.x, self.pos.y))
        surface.blit(sprite, rect)

        health_ratio = max(0, self.hp) / self.max_hp
        bar_rect = pygame.Rect(rect.left, rect.top - 10, rect.width, 6)
        pygame.draw.rect(surface, (50, 20, 20), bar_rect, border_radius=3)
        pygame.draw.rect(
            surface,
            (80, 220, 100),
            pygame.Rect(bar_rect.x, bar_rect.y, int(bar_rect.width * health_ratio), bar_rect.height),
            border_radius=3,
        )


class Tower:
    def __init__(self, pos, tower_type):
        self.pos = pygame.Vector2(pos)
        stats = TOWER_TYPES[tower_type]
        self.tower_type = tower_type
        self.range = stats["range"]
        self.fire_rate = stats["fire_rate"]
        self.damage = stats["damage"]
        self.color = stats["color"]
        self.cooldown = 0

    def update(self, dt, enemies, bullets):
        self.cooldown = max(0, self.cooldown - dt)
        for enemy in enemies:
            if enemy.alive and self.pos.distance_to(enemy.pos) <= self.range:
                if self.cooldown == 0:
                    bullets.append(Projectile(self.pos, enemy, self.damage))
                    self.cooldown = self.fire_rate
                break

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, self.pos, 17)
        pygame.draw.circle(surface, (230, 230, 240), self.pos, 17, 2)
        pygame.draw.circle(surface, (25, 25, 35), self.pos, 6)


class Projectile:
    def __init__(self, pos, target, damage):
        self.pos = pygame.Vector2(pos)
        self.target = target
        self.speed = 325
        self.damage = damage

    def update(self, dt):
        if not self.target.alive:
            return False

        direction = self.target.pos - self.pos
        if direction.length() < 12:
            self.target.hp -= self.damage
            if self.target.hp <= 0:
                self.target.alive = False
            return False

        self.pos += direction.normalize() * self.speed * dt
        return True

    def draw(self, surface):
        pygame.draw.circle(surface, (255, 220, 100), self.pos, 5)


def draw_background(surface):
    surface.fill((18, 27, 24))
    for y in range(0, BASE_HEIGHT, 80):
        color = (24 + y // 24, 48 + y // 20, 38 + y // 18)
        pygame.draw.rect(surface, color, (0, y, BASE_WIDTH - SHOP_WIDTH, 80))


def draw_path(surface):
    pygame.draw.lines(surface, (28, 20, 12), False, PATH_POINTS, PATH_WIDTH + 10)
    pygame.draw.lines(surface, (215, 214, 196), False, PATH_POINTS, PATH_WIDTH)
    pygame.draw.lines(surface, (168, 155, 132), False, PATH_POINTS, PATH_WIDTH - 14)


def draw_shop(surface, selected, money, lives, wave_count):
    panel = pygame.Rect(BASE_WIDTH - SHOP_WIDTH, 0, SHOP_WIDTH, BASE_HEIGHT)
    pygame.draw.rect(surface, (32, 35, 42), panel)
    pygame.draw.line(surface, (80, 86, 98), panel.topleft, panel.bottomleft, 3)

    title = FONT.render("TOWERS", True, (238, 240, 245))
    surface.blit(title, (panel.x + 20, 24))

    for name, rect in BUTTONS.items():
        active = name == selected
        bg = (145, 132, 74) if active else (72, 76, 86)
        pygame.draw.rect(surface, bg, rect, border_radius=10)
        pygame.draw.rect(surface, (230, 230, 235), rect, 2, border_radius=10)
        text = SMALL_FONT.render(f"{name.upper()}  ${TOWER_TYPES[name]['cost']}", True, (255, 255, 255))
        surface.blit(text, (rect.x + 12, rect.y + 26))

    hud_lines = [
        f"Money: ${money}",
        f"Lives: {lives}",
        f"Wave: {wave_count}",
        "",
        "Click the panel",
        "to switch towers.",
        "Click the field",
        "to place one.",
    ]
    y = BASE_HEIGHT - 220
    for line in hud_lines:
        if line:
            surface.blit(SMALL_FONT.render(line, True, (214, 219, 225)), (panel.x + 20, y))
        y += 24


def main():
    enemies = []
    towers = []
    bullets = []

    money = STARTING_MONEY
    lives = STARTING_LIVES
    selected = "basic"
    wave_count = 0
    last_spawn = pygame.time.get_ticks()
    next_skin = 0
    skins = ["alien", "ufo"]
    running = True

    while running:
        dt = CLOCK.tick(FPS) / 1000

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                if mx >= BASE_WIDTH - SHOP_WIDTH:
                    for name, rect in BUTTONS.items():
                        if rect.collidepoint((mx, my)):
                            selected = name
                            break
                else:
                    cost = TOWER_TYPES[selected]["cost"]
                    if money >= cost and not point_on_path((mx, my)):
                        towers.append(Tower((mx, my), selected))
                        money -= cost

        now = pygame.time.get_ticks()
        if now - last_spawn >= SPAWN_INTERVAL_MS:
            enemies.append(Enemy(skins[next_skin]))
            next_skin = (next_skin + 1) % len(skins)
            wave_count += 1
            last_spawn = now

        for enemy in enemies[:]:
            if not enemy.update(dt):
                if enemy.reached:
                    lives -= 1
                elif not enemy.alive:
                    money += enemy.reward
                enemies.remove(enemy)

        for tower in towers:
            tower.update(dt, enemies, bullets)

        bullets[:] = [bullet for bullet in bullets if bullet.update(dt)]

        draw_background(SCREEN)
        draw_path(SCREEN)

        for tower in towers:
            tower.draw(SCREEN)
        for enemy in enemies:
            enemy.draw(SCREEN)
        for bullet in bullets:
            bullet.draw(SCREEN)

        draw_shop(SCREEN, selected, money, lives, wave_count)

        if lives <= 0:
            over = FONT.render("Game Over - press ESC", True, (255, 240, 240))
            SCREEN.blit(over, (40, 50))
        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()








import sys
import pygame


pygame.init()


# ===== FULLSCREEN SETUP =====
screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h


FPS = 60
SPAWN_INTERVAL = 2000
STARTING_MONEY = 100
STARTING_LIVES = 10
PATH_WIDTH = 34


SHOP_WIDTH = 220
GAME_WIDTH = WIDTH - SHOP_WIDTH


clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)


# ===== TOWERS =====
TOWER_TYPES = {
    "basic": {"cost": 25, "range": 140, "fire_rate": 0.8, "damage": 1, "color": (60, 90, 170)},
    "sniper": {"cost": 60, "range": 260, "fire_rate": 1.8, "damage": 3, "color": (150, 60, 180)},
    "rapid": {"cost": 40, "range": 100, "fire_rate": 0.25, "damage": 0.5, "color": (200, 140, 60)},
}


# ===== PATH =====
PATH_POINTS = [
    (20,35),(70,80),(70,250),(220,250),(240,90),(340,40),
    (480,40),(530,80),(530,300),(620,300),(620,155),
    (740,155),(760,180),(760,455),(610,455),(480,445),
    (110,445),(75,500),(20,540),
]


# ===== ENEMY =====
class Enemy:
    def __init__(self):
        self.pos = pygame.Vector2(PATH_POINTS[0])
        self.index = 1
        self.speed = 120
        self.hp = 3
        self.radius = 12
        self.alive = True
        self.reached = False


    def update(self, dt):
        if not self.alive:
            return False


        if self.index >= len(PATH_POINTS):
            self.reached = True
            return False


        target = pygame.Vector2(PATH_POINTS[self.index])
        direction = target - self.pos


        if direction.length() == 0:
            self.index += 1
            return True


        step = self.speed * dt
        if step >= direction.length():
            self.pos = target
            self.index += 1
        else:
            self.pos += direction.normalize() * step


        return True


    def draw(self):
        pygame.draw.circle(screen, (200,60,60), self.pos, self.radius)


# ===== TOWER =====
class Tower:
    def __init__(self, pos, ttype):
        self.pos = pygame.Vector2(pos)
        stats = TOWER_TYPES[ttype]


        self.range = stats["range"]
        self.fire_rate = stats["fire_rate"]
        self.damage = stats["damage"]
        self.color = stats["color"]


        self.cooldown = 0


    def update(self, dt, enemies, bullets):
        self.cooldown = max(0, self.cooldown - dt)


        for e in enemies:
            if e.alive and self.pos.distance_to(e.pos) <= self.range:
                if self.cooldown == 0:
                    bullets.append(Projectile(self.pos, e, self.damage))
                    self.cooldown = self.fire_rate
                break


    def draw(self):
        pygame.draw.circle(screen, self.color, self.pos, 16)


# ===== PROJECTILE =====
class Projectile:
    def __init__(self, pos, target, dmg):
        self.pos = pygame.Vector2(pos)
        self.target = target
        self.speed = 300
        self.dmg = dmg


    def update(self, dt):
        if not self.target.alive:
            return False


        direction = self.target.pos - self.pos


        if direction.length() < 10:
            self.target.hp -= self.dmg
            if self.target.hp <= 0:
                self.target.alive = False
            return False


        self.pos += direction.normalize() * self.speed * dt
        return True


    def draw(self):
        pygame.draw.circle(screen, (255,220,100), self.pos, 4)


# ===== GAME STATE =====
enemies = []
towers = []
bullets = []


money = STARTING_MONEY
lives = STARTING_LIVES
selected = "basic"


last_spawn = pygame.time.get_ticks()


# ===== MAIN LOOP =====
running = True
while running:
    dt = clock.tick(FPS) / 1000


    # -------- EVENTS --------
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False


        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False


        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos


            # SHOP CLICK
            if mx > GAME_WIDTH:
                for name, rect in buttons.items():
                    if rect.collidepoint((mx, my)):
                        selected = name


            # PLACE TOWER
            else:
                cost = TOWER_TYPES[selected]["cost"]
                if money >= cost:
                    towers.append(Tower((mx, my), selected))
                    money -= cost


    # -------- SPAWN --------
    if pygame.time.get_ticks() - last_spawn > SPAWN_INTERVAL:
        enemies.append(Enemy())
        last_spawn = pygame.time.get_ticks()


    # -------- UPDATE --------
    for e in enemies[:]:
        if not e.update(dt):
            if e.reached:
                lives -= 1
            enemies.remove(e)


    for t in towers:
        t.update(dt, enemies, bullets)


    bullets[:] = [b for b in bullets if b.update(dt)]


    # -------- DRAW --------
    screen.fill((120,140,110))


    # PATH
    pygame.draw.lines(screen,(0,0,0),False,PATH_POINTS,PATH_WIDTH+8)
    pygame.draw.lines(screen,(240,240,230),False,PATH_POINTS,PATH_WIDTH)


    for t in towers: t.draw()
    for e in enemies: e.draw()
    for b in bullets: b.draw()


    # SHOP
    buttons = {}
    panel = pygame.Rect(GAME_WIDTH, 0, SHOP_WIDTH, HEIGHT)
    pygame.draw.rect(screen, (40,40,40), panel)


    y = 80
    for name, data in TOWER_TYPES.items():
        rect = pygame.Rect(GAME_WIDTH+20, y, SHOP_WIDTH-40, 70)


        color = (150,150,80) if selected == name else (80,80,80)
        pygame.draw.rect(screen, color, rect)


        txt = font.render(f"{name}  ${data['cost']}", True, (255,255,255))
        screen.blit(txt, (rect.x+10, rect.y+25))


        buttons[name] = rect
        y += 90


    # HUD
    hud = font.render(f"Money: {money}   Lives: {lives}", True, (255,255,255))
    screen.blit(hud, (20,20))


    pygame.display.flip()


    if lives <= 0:
        running = False


pygame.quit()
sys.exit()

