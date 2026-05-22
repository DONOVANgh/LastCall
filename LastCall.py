import math
import re
import sys
import tempfile
from pathlib import Path

import pygame

import os


pygame.init()

BASE_WIDTH = 1280
BASE_HEIGHT = 720
SHOP_WIDTH = 300
FPS = 60
SPAWN_INTERVAL_MS = 1450
STARTING_MONEY = 125
STARTING_LIVES = 10
PATH_WIDTH = 44
SELL_REFUND_RATE = 0.7

ART_FILE = Path(__file__).with_name("art.html")

SCREEN = pygame.display.set_mode((BASE_WIDTH, BASE_HEIGHT))
pygame.display.set_caption("Alien Track Defense")
CLOCK = pygame.time.Clock()
FONT = pygame.font.SysFont("consolas", 24)
SMALL_FONT = pygame.font.SysFont("consolas", 17)
TINY_FONT = pygame.font.SysFont("consolas", 14)

TOWER_TYPES = {
    "gunsman": {
        "label": "Gunsman",
        "cost": 40,
        "range": 180,
        "fire_rate": 0.7,
        "damage": 1.2,
        "color": (68, 118, 190),
        "projectile_color": (255, 225, 115),
        "projectile_speed": 395,
        "size": 18
    },
    "boxer": {
        "label": "Boxer",
        "cost": 55,
        "range": 72,
        "fire_rate": 0.45,
        "damage": 2.8,
        "color": (195, 72, 72),
        "projectile_color": (255, 140, 110),
        "projectile_speed": 300,
        "size": 19,
    },
    "support": {
        "label": "Support",
        "cost": 65,
        "range": 155,
        "fire_rate": 1.05,
        "damage": 0,
        "color": (96, 180, 118),
        "projectile_color": (132, 255, 185),
        "projectile_speed": 245,
        "size": 17,
        "buff_damage": 1.35,
        "buff_attack_speed": 0.72,
        "buff_duration": 3.2,
    },
    "slingshot": {
        "label": "Sling Shoter",
        "cost": 80,
        "range": 165,
        "fire_rate": 1.85,
        "damage": 0.95,
        "color": (156, 102, 58),
        "projectile_color": (205, 175, 120),
        "projectile_speed": 345,
        "size": 18,
        "shots": 3,
        "spread": 0.18,
    },
}

BASE_PATH_POINTS = [
    (28, 40), (84, 88), (84, 240), (220, 240), (258, 92), (348, 48),
    (490, 48), (548, 102), (548, 286), (646, 286), (646, 148),
    (766, 148), (790, 186), (790, 462), (620, 462), (492, 448),
    (144, 448), (94, 512), (28, 554),
]


# Load in image and place it on the map 
SPRITE_IMAGES = {
    "alien": "Assets/alien.png",
    "ufo": "Assets/ufo.png",
    "samurai": "Assets/samurai.png",
}   

def load_art_surfaces():
    surfaces = {}

    for name, filename in SPRITE_IMAGES.items():
        image = pygame.image.load(filename).convert_alpha()

        # Different sizes for enemies
        if name == "alien":
            image = pygame.transform.scale(image, (80, 80))

        elif name == "ufo":
            image = pygame.transform.scale(image, (70, 50))
        
        elif name == "samurai":
            image = pygame.transform.scale(image, (60, 80))

        surfaces[name] = image

    return surfaces


ART_SURFACES = load_art_surfaces()


def build_buttons():
    buttons = {}
    y = 88
    for name in TOWER_TYPES:
        buttons[name] = pygame.Rect(BASE_WIDTH - SHOP_WIDTH + 20, y, SHOP_WIDTH - 40, 72)
        y += 92
    return buttons


def scale_path(points):
    game_width = BASE_WIDTH - SHOP_WIDTH
    x_scale = game_width / 840
    y_scale = BASE_HEIGHT / 590
    return [(int(x * x_scale), int(y * y_scale)) for x, y in points]


PATH_POINTS = scale_path(BASE_PATH_POINTS)
BUTTONS = build_buttons()
PLAYFIELD_RECT = pygame.Rect(0, 0, BASE_WIDTH - SHOP_WIDTH, BASE_HEIGHT)


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

class Enemy:
    def __init__(self, skin_name):
        self.skin_name = skin_name

        # Set enemy image
        self.sprite = ART_SURFACES[skin_name]

        self.pos = pygame.Vector2(PATH_POINTS[0])
        self.index = 1
        self.speed = 102 if skin_name == "alien" else 136
        self.hp = 4 if skin_name == "alien" else 3
        self.max_hp = self.hp
        self.alive = True
        self.reached = False
        self.reward = 12 if skin_name == "alien" else 10
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
        self.label = stats["label"]
        self.cost = stats["cost"]
        self.base_range = stats["range"]
        self.base_fire_rate = stats["fire_rate"]
        self.base_damage = stats["damage"]
        self.range = self.base_range
        self.fire_rate = self.base_fire_rate
        self.damage = self.base_damage
        self.color = stats["color"]
        self.projectile_color = stats["projectile_color"]
        self.projectile_speed = stats["projectile_speed"]
        self.size = stats["size"]
        self.cooldown = 0
        self.buff_timer = 0
        self.buff_damage_mult = 1.0
        self.buff_speed_mult = 1.0
        self.support_fx_timer = 0

    @property
    def sell_value(self):
        return max(1, int(self.cost * SELL_REFUND_RATE))

    def contains_point(self, point):
        return self.pos.distance_to(pygame.Vector2(point)) <= self.size + 8

    def apply_support_buff(self, damage_mult, speed_mult, duration):
        self.buff_damage_mult = max(self.buff_damage_mult, damage_mult)
        self.buff_speed_mult = min(self.buff_speed_mult, speed_mult)
        self.buff_timer = max(self.buff_timer, duration)
        self.support_fx_timer = max(self.support_fx_timer, 0.25)

    def effective_damage(self):
        return self.base_damage * self.buff_damage_mult

    def effective_fire_rate(self):
        return self.base_fire_rate * self.buff_speed_mult

    def update(self, dt, enemies, towers, projectiles):
        self.cooldown = max(0, self.cooldown - dt)
        self.support_fx_timer = max(0, self.support_fx_timer - dt)
        if self.buff_timer > 0:
            self.buff_timer = max(0, self.buff_timer - dt)
            if self.buff_timer == 0:
                self.buff_damage_mult = 1.0
                self.buff_speed_mult = 1.0

        if self.tower_type == "support":
            self._update_support(enemies, towers, projectiles)
        else:
            self._update_attack(enemies, projectiles)

    def _update_attack(self, enemies, projectiles):
        for enemy in enemies:
            if enemy.alive and self.pos.distance_to(enemy.pos) <= self.range:
                if self.cooldown == 0:
                    self._fire(enemy, projectiles)
                    self.cooldown = self.effective_fire_rate()
                break

    def _update_support(self, enemies, towers, projectiles):
        candidates = []
        for tower in towers:
            if tower is self or tower.tower_type == "support":
                continue
            if self.pos.distance_to(tower.pos) <= self.range:
                score = tower.buff_timer
                if any(enemy.alive and tower.pos.distance_to(enemy.pos) <= tower.range for enemy in enemies):
                    score -= 1.0
                candidates.append((score, tower))

        if candidates and self.cooldown == 0:
            _, ally = min(candidates, key=lambda item: item[0])
            stats = TOWER_TYPES["support"]
            projectiles.append(
                SupportProjectile(
                    self.pos,
                    ally,
                    stats["buff_damage"],
                    stats["buff_attack_speed"],
                    stats["buff_duration"],
                    self.projectile_color,
                )
            )
            self.cooldown = self.base_fire_rate

    def _fire(self, enemy, projectiles):
        if self.tower_type == "slingshot":
            origin = enemy.pos - self.pos
            angle = math.atan2(origin.y, origin.x)
            shots = TOWER_TYPES["slingshot"]["shots"]
            spread = TOWER_TYPES["slingshot"]["spread"]
            for shot_index in range(shots):
                offset = (shot_index - (shots - 1) / 2) * spread
                projectiles.append(
                    Projectile(
                        self.pos,
                        enemy,
                        self.effective_damage(),
                        self.projectile_speed,
                        self.projectile_color,
                        angle_offset=offset,
                    )
                )
        else:
            projectiles.append(
                Projectile(
                    self.pos,
                    enemy,
                    self.effective_damage(),
                    self.projectile_speed,
                    self.projectile_color,
                )
            )

    def draw(self, surface, selected=False):
        outline = (255, 241, 185) if selected else (235, 235, 240)
        buff_ring = (110, 255, 175) if self.buff_timer > 0 or self.support_fx_timer > 0 else None

        if buff_ring:
            radius = self.size + 8 + int(self.support_fx_timer * 8)
            pygame.draw.circle(surface, buff_ring, self.pos, radius, 2)

        pygame.draw.circle(surface, self.color, self.pos, self.size)
        pygame.draw.circle(surface, outline, self.pos, self.size, 2)

        if self.tower_type == "gunsman":
            pygame.draw.rect(surface, (30, 34, 44), (self.pos.x - 4, self.pos.y - 11, 8, 14), border_radius=2)
            pygame.draw.rect(surface, (70, 70, 75), (self.pos.x + 2, self.pos.y - 10, 14, 4), border_radius=2)
        elif self.tower_type == "boxer":
            pygame.draw.circle(surface, (255, 214, 186), (int(self.pos.x), int(self.pos.y - 9)), 6)
            pygame.draw.circle(surface, (255, 110, 110), (int(self.pos.x - 9), int(self.pos.y + 2)), 5)
            pygame.draw.circle(surface, (255, 110, 110), (int(self.pos.x + 9), int(self.pos.y + 2)), 5)
        elif self.tower_type == "support":
            pygame.draw.circle(surface, (240, 252, 205), self.pos, 6)
            pygame.draw.circle(surface, (200, 255, 220), (int(self.pos.x), int(self.pos.y - 9)), 3)
            pygame.draw.circle(surface, (200, 255, 220), (int(self.pos.x - 8), int(self.pos.y + 5)), 3)
            pygame.draw.circle(surface, (200, 255, 220), (int(self.pos.x + 8), int(self.pos.y + 5)), 3)
        elif self.tower_type == "slingshot":
            pygame.draw.line(surface, (60, 42, 24), (self.pos.x - 8, self.pos.y + 8), (self.pos.x - 1, self.pos.y - 9), 3)
            pygame.draw.line(surface, (60, 42, 24), (self.pos.x + 8, self.pos.y + 8), (self.pos.x + 1, self.pos.y - 9), 3)
            pygame.draw.line(surface, (150, 120, 92), (self.pos.x - 1, self.pos.y - 9), (self.pos.x + 1, self.pos.y - 9), 2)


class Projectile:
    def __init__(self, pos, target, damage, speed, color, angle_offset=0.0):
        self.pos = pygame.Vector2(pos)
        self.target = target
        self.speed = speed
        self.damage = damage
        self.color = color
        self.radius = 5
        self.angle_offset = angle_offset

    def update(self, dt):
        if not self.target.alive:
            return False

        direction = self.target.pos - self.pos
        if direction.length_squared() == 0:
            return False

        if self.angle_offset:
            direction = direction.rotate_rad(self.angle_offset)

        if self.pos.distance_to(self.target.pos) < 14:
            self.target.hp -= self.damage
            if self.target.hp <= 0:
                self.target.alive = False
            return False

        self.pos += direction.normalize() * self.speed * dt
        return True

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, self.pos, self.radius)
        pygame.draw.circle(surface, (70, 45, 20), self.pos, self.radius, 1)


class SupportProjectile:
    def __init__(self, pos, target_tower, damage_mult, speed_mult, duration, color):
        self.pos = pygame.Vector2(pos)
        self.target_tower = target_tower
        self.damage_mult = damage_mult
        self.speed_mult = speed_mult
        self.duration = duration
        self.speed = 230
        self.color = color
        self.radius = 6

    def update(self, dt):
        direction = self.target_tower.pos - self.pos
        if direction.length() < 12:
            self.target_tower.apply_support_buff(self.damage_mult, self.speed_mult, self.duration)
            return False

        self.pos += direction.normalize() * self.speed * dt
        return True

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, self.pos, self.radius)
        pygame.draw.circle(surface, (240, 255, 245), self.pos, self.radius - 2)


def draw_background(surface):
    surface.fill((17, 28, 24))

    for y in range(0, BASE_HEIGHT, 72):
        band_color = (22 + y // 28, 48 + y // 22, 34 + y // 24)
        pygame.draw.rect(surface, band_color, (0, y, PLAYFIELD_RECT.width, 72))

    for x in range(24, PLAYFIELD_RECT.width - 20, 140):
        pygame.draw.circle(surface, (30, 70, 48), (x, 42), 18)
        pygame.draw.circle(surface, (26, 58, 42), (x + 26, BASE_HEIGHT - 34), 14)

    frame = PLAYFIELD_RECT.inflate(-18, -18)
    pygame.draw.rect(surface, (110, 97, 66), frame, 8, border_radius=16)
    pygame.draw.rect(surface, (56, 84, 54), frame.inflate(-16, -16), 5, border_radius=12)


def draw_path(surface):
    pygame.draw.lines(surface, (76, 60, 40), False, PATH_POINTS, PATH_WIDTH + 16)
    pygame.draw.lines(surface, (34, 26, 18), False, PATH_POINTS, PATH_WIDTH + 6)
    pygame.draw.lines(surface, (214, 205, 176), False, PATH_POINTS, PATH_WIDTH)
    pygame.draw.lines(surface, (164, 148, 112), False, PATH_POINTS, PATH_WIDTH - 14)

    for point in PATH_POINTS[1:-1]:
        pygame.draw.circle(surface, (126, 112, 88), point, 7)


def draw_shop(surface, selected, money, lives, wave_count, sell_preview):
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
        text = SMALL_FONT.render(f"{TOWER_TYPES[name]['label']}  ${TOWER_TYPES[name]['cost']}", True, (255, 255, 255))
        surface.blit(text, (rect.x + 12, rect.y + 14))
        desc = {
            "gunsman": "Good range, steady shots",
            "boxer": "Melee bruiser, big hits",
            "support": "Throws buffs to towers",
            "slingshot": "3 shots at once, slow reload",
        }[name]
        surface.blit(TINY_FONT.render(desc, True, (220, 223, 228)), (rect.x + 12, rect.y + 42))

    hud_lines = [
        f"Money: ${money}",
        f"Lives: {lives}",
        f"Wave: {wave_count}",
        "",
        "Left click: place / select",
        "Right click: sell tower",
        f"Sell refund: {int(SELL_REFUND_RATE * 100)}%",
    ]
    y = BASE_HEIGHT - 198
    for line in hud_lines:
        if line:
            surface.blit(SMALL_FONT.render(line, True, (214, 219, 225)), (panel.x + 20, y))
        y += 24

    if sell_preview:
        preview = SMALL_FONT.render(sell_preview, True, (250, 228, 166))
        surface.blit(preview, (panel.x + 20, BASE_HEIGHT - 42))


def draw_selection(surface, selected_tower, mouse_pos):
    if selected_tower is not None:
        pygame.draw.circle(surface, (240, 226, 136), selected_tower.pos, selected_tower.range, 1)
        label = SMALL_FONT.render(f"Sell for ${selected_tower.sell_value}", True, (255, 239, 186))
        surface.blit(label, (selected_tower.pos.x - 42, selected_tower.pos.y - selected_tower.size - 28))
    elif mouse_pos[0] < PLAYFIELD_RECT.width:
        selected_stats = TOWER_TYPES[mouse_pos[2]]
        good_spot = not point_on_path(mouse_pos[:2], margin=24)
        ring_color = (100, 230, 145) if good_spot else (235, 104, 104)
        pygame.draw.circle(surface, ring_color, mouse_pos[:2], selected_stats["range"], 1)


def find_tower_at(towers, point):
    for tower in reversed(towers):
        if tower.contains_point(point):
            return tower
    return None


def can_place_tower(towers, point, tower_type):
    if not PLAYFIELD_RECT.collidepoint(point):
        return False
    if point_on_path(point):
        return False
    candidate_size = TOWER_TYPES[tower_type]["size"]
    for tower in towers:
        if tower.pos.distance_to(pygame.Vector2(point)) < tower.size + candidate_size + 10:
            return False
    return True


def main():
    enemies = []
    towers = []
    projectiles = []

    money = STARTING_MONEY
    lives = STARTING_LIVES
    selected = "gunsman"
    selected_tower = None
    wave_count = 0
    last_spawn = pygame.time.get_ticks()
    next_skin = 0
    skins = ["alien", "ufo", "samurai"]
    running = True

    while running:
        dt = CLOCK.tick(FPS) / 1000
        mouse_x, mouse_y = pygame.mouse.get_pos()

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
                            selected_tower = None
                            break
                else:
                    clicked_tower = find_tower_at(towers, (mx, my))
                    if clicked_tower:
                        selected_tower = clicked_tower
                    else:
                        cost = TOWER_TYPES[selected]["cost"]
                        if money >= cost and can_place_tower(towers, (mx, my), selected):
                            towers.append(Tower((mx, my), selected))
                            money -= cost
                            selected_tower = towers[-1]
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                clicked_tower = find_tower_at(towers, event.pos)
                if clicked_tower:
                    money += clicked_tower.sell_value
                    towers.remove(clicked_tower)
                    selected_tower = None

        now = pygame.time.get_ticks()
        if lives > 0 and now - last_spawn >= SPAWN_INTERVAL_MS:
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
            tower.update(dt, enemies, towers, projectiles)

        projectiles[:] = [projectile for projectile in projectiles if projectile.update(dt)]

        if selected_tower not in towers:
            selected_tower = None

        draw_background(SCREEN)
        draw_path(SCREEN)

        hover_tower = find_tower_at(towers, (mouse_x, mouse_y))
        active_tower = hover_tower or selected_tower

        for tower in towers:
            tower.draw(SCREEN, selected=(tower is active_tower))
        for enemy in enemies:
            enemy.draw(SCREEN)
        for projectile in projectiles:
            projectile.draw(SCREEN)

        draw_selection(SCREEN, active_tower, (mouse_x, mouse_y, selected))
        sell_preview = ""
        if hover_tower:
            sell_preview = f"{hover_tower.label}: sell for ${hover_tower.sell_value}"
        draw_shop(SCREEN, selected, money, lives, wave_count, sell_preview)

        if lives <= 0:
            overlay = pygame.Surface((PLAYFIELD_RECT.width, BASE_HEIGHT), pygame.SRCALPHA)
            overlay.fill((20, 12, 12, 125))
            SCREEN.blit(overlay, (0, 0))
            over = FONT.render("Game Over - press ESC", True, (255, 240, 240))
            SCREEN.blit(over, (42, 52))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()





