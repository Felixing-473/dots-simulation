import pygame
import random
import math

# --- 初始化 ---
pygame.init()
PANEL_W = 180
VAULT_W, VAULT_H = 200, 160
WIDTH, HEIGHT = 1180, 720
CANVAS_W = WIDTH - PANEL_W
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("生命方程粒子模拟器 v4")
clock = pygame.time.Clock()
FPS = 60

FONT_XS = pygame.font.SysFont("microsoftyahei", 11)
FONT_LG = pygame.font.SysFont("microsoftyahei", 20)

WIND = {"angle": 0.4, "strength": 1}
MOVE_SCALE = 0.38
STABLE_THRESHOLD = 10
COLLISION_SEPARATION = True   # 碰撞后轻推分离，避免长期重叠
LIFE_COLOR = (255, 220, 120)
STABLE_COLOR = (180, 190, 210)

# 交替场态模数 — 三维度独立
ALT_MZ, ALT_MD, ALT_MS = 11, 17, 23

PARTICLE_DATA = [
    {"color": (135, 206, 235), "move": "linear",    "name": "天蓝"},
    {"color": (152, 251, 152), "move": "oscillate", "name": "薄荷"},
    {"color": (255, 196, 112), "move": "spiral",    "name": "浅橙"},
    {"color": (216, 191, 216), "move": "wander",    "name": "淡紫"},
    {"color": (248, 248, 248), "move": "follow",    "name": "奶白"},
    {"color": (205, 92, 92),   "move": "rush",      "name": "砖红"},
    {"color": (212, 175, 55),  "move": "chaos",     "name": "土黄"},
    {"color": (112, 128, 144), "move": "avoid",     "name": "灰蓝"},
    {"color": (255, 182, 193), "move": "orbit",     "name": "桃粉"},
    {"color": (47, 79, 79),    "move": "patrol",    "name": "深青"},
]

# 碰撞表 — 序数 Z 变化大，电子 D 中等，时间 S 常重置/微调
# (dZ, dD, dS)
COLLISION_TABLE = {
    (1, 2): (2, 1, 0),   (2, 1): (1, 2, 5),
    (2, 3): (-1, 3, 0),  (3, 2): (1, -2, 3),
    (3, 4): (-2, 0, -2), (4, 3): (-1, 1, 2),
    (4, 5): (0, 2, 1),   (5, 4): (1, 0, 0),
    (5, 6): (-2, -3, 0),(6, 5): (-1, -2, 8),
    (6, 7): (2, 1, -5),  (7, 6): (1, 2, 0),
    (7, 8): (0, -3, 2),  (8, 7): (-1, 0, 0),
    (8, 9): (1, 2, 0),   (9, 8): (1, 1, -3),
    (9, 10): (-2, 0, -2),(10, 9): (-1, 0, 0),
}
for k in range(1, 9):
    COLLISION_TABLE[(10, k)] = (-1, 2, 4)
    COLLISION_TABLE[(k, 10)] = (1, -1, 2)


# =============================================================================
#  幅度函数 behavior_scale
#  D 主导即时幅度；S 短期几乎无感，长期 sqrt 累积 → 日积月累
# =============================================================================
def behavior_scale(d, s):
    d, s = int(d), int(s)
    return max(1, d // 2 + int(math.sqrt(max(0, s))))


# =============================================================================
#  交替核心 alternate_broadcast / alternate_receive
#
#  输入 (Z, D, S) → 输出 (Bz, Bd, Bs) 三个独立「场态」
#    Bz = 序场态 — Z 的类型投影，S 长期才渗入
#    Bd = 电场态 — D 的幅度投影
#    Bs = 时场态 — S 的累积投影（÷8 使短期稳定、长期才变）
#
#  receive 为 broadcast 的模补集 → 寻对目标
#  生命合成：A.broadcast == B.receive 且 B.broadcast == A.receive（完全对偶）
# =============================================================================
def alternate_broadcast(z, d, s):
    z, d, s = int(z), int(d), int(s)
    return (
        (z * 5 + s // 20) % ALT_MZ,
        (d * 3 + z) % ALT_MD,
        (s // 8 + d * 2) % ALT_MS,
    )


def alternate_receive(z, d, s):
    bz, bd, bs = alternate_broadcast(z, d, s)
    return (
        (ALT_MZ - bz) % ALT_MZ,
        (ALT_MD - bd) % ALT_MD,
        (ALT_MS - bs) % ALT_MS,
    )


def alternate_field_overlap(z1, d1, s1, z2, d2, s2):
    """两粒子 broadcast 场态逐维对比 → 重叠数 0~3（阶段判定用）"""
    b1 = alternate_broadcast(z1, d1, s1)
    b2 = alternate_broadcast(z2, d2, s2)
    return sum(int(b1[i] == b2[i]) for i in range(3))


def alternate_resonance(za, da, sa, zb, db, sb):
    """A 的 broadcast 与 B 的 receive 逐维吻合数 0~3"""
    ba = alternate_broadcast(za, da, sa)
    rb = alternate_receive(zb, db, sb)
    return sum(int(ba[i] == rb[i]) for i in range(3))


def alternate_is_complement(za, da, sa, zb, db, sb):
    """双向共振均 = 3 → 完全对偶"""
    return (alternate_resonance(za, da, sa, zb, db, sb) == 3 and
            alternate_resonance(zb, db, sb, za, da, sa) == 3)


def alternate_can_life(za, da, sa, zb, db, sb):
    """生命合成：完全对偶，或双向共振≥2且场态重叠≥2"""
    ra = alternate_resonance(za, da, sa, zb, db, sb)
    rb = alternate_resonance(zb, db, sb, za, da, sa)
    ov = alternate_field_overlap(za, da, sa, zb, db, sb)
    if alternate_is_complement(za, da, sa, zb, db, sb):
        return True
    return ra >= 2 and rb >= 2 and ov >= 2


def alternate_func(p, particles):
    """
    对粒子 p：遍历全场，返回
      - best_overlap : 与其他粒子 broadcast 最高重叠 (0~3)
      - best_partner : 共振度最高的配对
      - best_resonance : 最高单向共振 (0~3)
    """
    best_overlap = 0
    best_resonance = 0
    best_partner = None
    for q in particles:
        if q is p or not q.alive or q.stable:
            continue
        ov = alternate_field_overlap(p.Z, p.D, p.S, q.Z, q.D, q.S)
        rs = alternate_resonance(p.Z, p.D, p.S, q.Z, q.D, q.S)
        if ov > best_overlap:
            best_overlap = ov
        if rs > best_resonance:
            best_resonance = rs
            best_partner = q
    return best_overlap, best_partner, best_resonance


# =============================================================================
#  TimeFunc — S 每帧 +1；不改 Z（序数只由碰撞改）
#  仅部分序列因自身行为规律微调 D
# =============================================================================
def time_func(p, particles):
    p.S = int(p.S) + 1
    if p.stable or p.Z <= 0:
        return

    z = p.Z
    nearby = sum(1 for q in particles if q is not p and q.alive
                 and math.hypot(q.x - p.x, q.y - p.y) < 140)
    same_z = sum(1 for q in particles if q is not p and q.alive and q.Z == z
                 and math.hypot(q.x - p.x, q.y - p.y) < 100)

    # 各序列：仅 D 受自身行为影响（幅度），Z 不动
    if z == 2 and p.S % 3 == 0:
        p.D = max(2, int(p.D) + (1 if math.sin(p.S * 0.2) > 0 else -1))
    elif z == 5 and nearby > 0:
        if p.S % 10 == 0:
            p.D = max(2, int(p.D) + nearby // 3)
    elif z == 8:
        isolated = all(q is p or not q.alive or math.hypot(q.x - p.x, q.y - p.y) > 170
                       for q in particles)
        if isolated and p.S % 8 == 0:
            p.D = int(p.D) + 1
    elif z == 9 and same_z >= 2 and p.S % 12 == 0:
        p.D = max(2, int(p.D) + 1)

    p.apply_state()


# =============================================================================
#  MoveFunc — Z 决定移动「类型」；behavior_scale(D,S) 决定「幅度」
# =============================================================================
def move_func(p, particles, wind, sim_speed):
    if not p.alive:
        return

    if p.stable:
        p._clamp_bounds()
        return

    z = min(p.Z, 10)
    sc = behavior_scale(p.D, p.S)
    speed = max(1, int(sc * sim_speed * MOVE_SCALE))
    mode = p.active_move()

    if mode == "linear":
        if z <= 3:
            speed = max(1, speed * 2 // 3)
        elif z >= 9:
            speed = int(speed * 3 // 2)
    elif mode == "oscillate":
        amp = sc // 2 + 1
        p.vx += int(math.sin(p.S * 0.15) * amp * 0.4)
        p.vy += int(math.cos(p.S * 0.12) * amp * 0.3)
    elif mode == "spiral":
        rate = sc // 3 + 1
        p.vx += int(math.cos(p.S * 0.08) * rate * 0.5)
        p.vy += int(math.sin(p.S * 0.08) * rate * 0.5)
    elif mode == "wander":
        if p.S % max(4, 12 - sc // 3) == 0:
            p.vx += random.randint(-sc // 2, sc // 2)
            p.vy += random.randint(-sc // 2, sc // 2)
    elif mode == "follow":
        pull = sc // 4 + 1
        for q in particles:
            if q is not p and q.alive and not q.stable:
                dx, dy = int(q.x - p.x), int(q.y - p.y)
                dist = math.hypot(dx, dy)
                reach = 80 + sc * 3
                if 0 < dist < reach:
                    p.vx += int(dx / dist * pull)
                    p.vy += int(dy / dist * pull)
    elif mode == "rush":
        if sc >= 8:
            p.vx = int(p.vx * 3 // 2)
            p.vy = int(p.vy * 3 // 2)
    elif mode == "chaos":
        if p.S % max(3, 8 - sc // 5) == 0:
            p.vx = random.randint(-speed, speed)
            p.vy = random.randint(-speed, speed)
    elif mode == "avoid":
        flee_r = 60 + sc * 2
        for q in particles:
            if q is p or not q.alive:
                continue
            dx, dy = int(p.x - q.x), int(p.y - q.y)
            dist = math.hypot(dx, dy)
            if 0 < dist < flee_r:
                f = sc // 3 + 1
                p.vx += int(dx / dist * f)
                p.vy += int(dy / dist * f)
    elif mode == "orbit":
        orbit_r = 50 + sc * 4
        for q in particles:
            if q.Z == p.Z and q is not p and q.alive:
                dx, dy = int(q.x - p.x), int(q.y - p.y)
                dist = math.hypot(dx, dy)
                if 0 < dist < orbit_r:
                    o = sc // 4 + 1
                    p.vx += int(-dy / dist * o)
                    p.vy += int(dx / dist * o)
    elif mode == "patrol":
        if sc >= 7 and p.S % 25 == 0:
            p.vx = random.randint(-speed, speed)
            p.vy = random.randint(-speed, speed)

    p.vx += int(math.cos(wind["angle"]) * wind["strength"] * sim_speed * MOVE_SCALE)
    p.vy += int(math.sin(wind["angle"]) * wind["strength"] * sim_speed * MOVE_SCALE)
    wind["angle"] += 0.002

    cap = speed + sc // 2 + 2
    p.vx = max(-cap, min(cap, int(p.vx)))
    p.vy = max(-cap, min(cap, int(p.vy)))
    p.x += int(p.vx * sim_speed * MOVE_SCALE)
    p.y += int(p.vy * sim_speed * MOVE_SCALE)
    p._clamp_bounds()


# =============================================================================
#  CollisionFunc — Z 强依赖碰撞；D/S 同步变化
# =============================================================================
def _collision_chaos(a, b):
    seed = (a.Z * 37 + a.D * 19 + a.S * 11 + b.Z * 31 + b.D * 23 + b.S * 13)
    r = seed % 125
    return ((r % 5) - 2, ((r // 5) % 5) - 2, ((r // 25) % 5) - 2)


def _lookup_delta(self_z, other_z):
    if (self_z, other_z) in COLLISION_TABLE:
        return COLLISION_TABLE[(self_z, other_z)]
    return (((self_z + other_z) % 3) - 1, 0, random.randint(0, 3))


def collision_func(a, b):
    za, zb = int(a.Z), int(b.Z)
    if za < 1 and zb < 1:
        return
    if za < 1 or zb < 1:
        return

    da = list(_lookup_delta(min(za, 10), min(zb, 10)))
    db = list(_lookup_delta(min(zb, 10), min(za, 10)))
    ca, cb = _collision_chaos(a, b), _collision_chaos(b, a)

    if za > STABLE_THRESHOLD:
        da[0] = da[0] // 2
        da[1] = da[1] // 2
    if zb > STABLE_THRESHOLD:
        db[0] = db[0] // 2
        db[1] = db[1] // 2

    factor = max(1, (min(za, 10) + min(zb, 10)) // 3)
    a.Z = max(0, za + int((da[0] + ca[0]) * factor // 2))
    b.Z = max(0, zb + int((db[0] + cb[0]) * factor // 2))
    a.D = max(0, int(a.D) + da[1] + ca[1])
    b.D = max(0, int(b.D) + db[1] + cb[1])
    a.S = max(0, int(a.S) + da[2] + ca[2])
    b.S = max(0, int(b.S) + db[2] + cb[2])

    if za != a.Z and zb != b.Z and (a.Z + b.Z + a.D + b.D) % 37 == 0:
        a.Z, b.Z = b.Z, a.Z

    if a.Z == 0 and b.Z >= 3:
        a.Z, b.Z = 1, b.Z - 1
    elif b.Z == 0 and a.Z >= 3:
        b.Z, a.Z = 1, a.Z - 1
    elif a.Z == 0 and b.Z <= 1:
        pass
    elif b.Z == 0 and a.Z <= 1:
        pass

    if a.Z == 6:
        a.S = 0
    if b.Z == 6:
        b.S = 0

    a.apply_state()
    b.apply_state()
    if COLLISION_SEPARATION:
        _separation_push(a, b)


def _separation_push(a, b):
    dx, dy = a.x - b.x, a.y - b.y
    dist = math.hypot(dx, dy)
    if dist < 0.5:
        dx, dy, dist = random.choice([(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1)])
    overlap = (a.radius + b.radius) - dist
    if overlap > 0:
        push = int(overlap // 2) + 1
        a.x += int(dx / dist * push)
        a.y += int(dy / dist * push)
        b.x -= int(dx / dist * push)
        b.y -= int(dy / dist * push)
        a._clamp_bounds()
        b._clamp_bounds()


# =============================================================================
#  SpecialCheckFunc — 邻近专属：主要改 D（幅度），不改 Z
# =============================================================================
def special_check_func(p, particles):
    if p.stable or not p.alive or p.Z <= 0:
        return
    z = p.Z
    for q in particles:
        if q is p or not q.alive:
            continue
        dist = math.hypot(p.x - q.x, p.y - q.y)
        if dist > 130:
            continue
        qz = q.Z
        if z == 2 and qz == 3 and dist < 55:
            p.D = max(2, int(p.D) + 1)
        elif z == 3 and qz == 4 and dist < 60 and p.S % 8 == 0:
            p.D = max(2, int(p.D) - 1)
        elif z == 5 and dist < 90 and p.S % 12 == 0:
            p.D = int(p.D) + 1
        elif z == 7 and qz == 8 and dist < 70:
            q.D = max(0, int(q.D) - 1)
        elif z == 9 and qz == p.Z and dist < 90:
            p.S = int(p.S) + 1
        elif z == 10 and 1 <= qz <= 8 and dist < 65 and p.S % 10 == 0:
            q.D = max(2, int(q.D) + 1)
            p.D = max(2, int(p.D) - 1)
    p.apply_state()


# =============================================================================
#  AlternateCheck — 阶段 1 躁动 / 阶段 2 改 D / 阶段 3 对偶合成
# =============================================================================
def alternate_apply_phases(particles):
    unrest, fluctuate, life_pairs = set(), set(), []
    checked = set()

    for p in particles:
        if not p.alive or p.stable or p.Z < 1:
            continue
        overlap, partner, resonance = alternate_func(p, particles)
        p.alt_phase = overlap
        p.alt_resonance = resonance

        if overlap == 1:
            unrest.add(p)
        elif overlap == 2:
            fluctuate.add(p)

        if partner and alternate_can_life(p.Z, p.D, p.S, partner.Z, partner.D, partner.S):
            pair = tuple(sorted([id(p), id(partner)]))
            if pair not in checked:
                checked.add(pair)
                life_pairs.append((p, partner))

    for p in fluctuate:
        p.D = max(2, int(p.D) + random.randint(-5, 5))
        p.S = max(0, int(p.S) + random.randint(-2, 2))
        p.apply_state()

    return unrest, fluctuate, life_pairs


# =============================================================================
#  LifeFunc
# =============================================================================
def life_spawn_calc(a, b):
    if not alternate_can_life(a.Z, a.D, a.S, b.Z, b.D, b.S):
        return None
    z_new = max(1, min(10, (a.Z + b.Z) // 2))
    d_new = max(2, (int(a.D) + int(b.D)) // 2 + 1)
    cx, cy = int((a.x + b.x) / 2), int((a.y + b.y) / 2)
    move_modes = list({data_for_z(a.Z)["move"], data_for_z(b.Z)["move"]})
    avg = tuple((a.color[i] + b.color[i]) // 2 for i in range(3))
    blend = tuple(min(255, (avg[i] + LIFE_COLOR[i]) // 2) for i in range(3))
    return {
        "Z": z_new, "D": d_new, "S": 0,
        "x": cx, "y": cy, "move_modes": move_modes,
        "mother_zs": [a.Z, b.Z], "color": blend,
    }


def clamp_canvas(x, y):
    return max(PANEL_W + 10, min(WIDTH - 10, x)), max(10, min(HEIGHT - 10, y))


def in_canvas(x, y):
    return PANEL_W <= x <= WIDTH - 10 and 10 <= y <= HEIGHT - 10


def data_for_z(z):
    if 1 <= z <= 10:
        return PARTICLE_DATA[z - 1]
    return {"color": STABLE_COLOR, "move": "stable", "name": "稳态"}


def stable_display_color(z):
    base_z = ((int(z) - 1) % 10) + 1
    bc = data_for_z(base_z)["color"]
    return tuple((bc[i] + STABLE_COLOR[i]) // 2 for i in range(3))


class Particle:
    def __init__(self, z, x=None, y=None, life_data=None):
        self.vx = random.randint(-1, 1)
        self.vy = random.randint(-1, 1)
        self.alive = True
        self.stable = False
        self.unrest = False
        self.alt_phase = 0
        self.alt_resonance = 0
        self.is_life = False
        self.move_idx = 0
        self.move_switch_timer = 0
        self.mother_zs = []
        self._applied_z = None
        self.uid = id(self)

        if life_data:
            self.is_life = True
            self.Z = int(life_data["Z"])
            self.D = int(life_data["D"])
            self.S = int(life_data["S"])
            self.x, self.y = life_data["x"], life_data["y"]
            self.color = life_data["color"]
            self.move_modes = life_data["move_modes"]
            self.mother_zs = life_data["mother_zs"]
        else:
            self.Z = int(z)
            self.D = int(z) * 2
            self.S = 0
            self.x = x if x is not None else random.randint(PANEL_W + 60, WIDTH - 60)
            self.y = y if y is not None else random.randint(60, HEIGHT - 60)
            self.color = data_for_z(self.Z)["color"]
            self.move_modes = [data_for_z(self.Z)["move"]]

        self.apply_state()

    def apply_state(self):
        self.Z, self.D, self.S = int(self.Z), int(self.D), int(self.S)
        if self.Z <= 0:
            self.alive = False
            return

        prev_z = self._applied_z
        self.stable = self.Z > STABLE_THRESHOLD

        if self.stable:
            self.color = stable_display_color(self.Z)
            sc = behavior_scale(self.D, self.S)
            self.radius = 8 + sc // 2
            self._applied_z = self.Z
            return

        if not self.is_life:
            self.color = data_for_z(self.Z)["color"]
            new_mode = data_for_z(min(self.Z, 10))["move"]
            if prev_z != self.Z:
                self.move_modes = [new_mode]
                self.move_idx = 0
                self.move_switch_timer = 0
            elif not self.move_modes or self.move_modes[0] != new_mode:
                self.move_modes = [new_mode]
                self.move_idx = 0
        elif prev_z is not None and prev_z != self.Z:
            nm = data_for_z(min(self.Z, 10))["move"]
            if nm not in self.move_modes:
                self.move_modes.append(nm)

        sc = behavior_scale(self.D, self.S)
        self.radius = {1: 12, 2: 11, 3: 10}.get(self.Z, 6 + sc // 2)
        self._applied_z = self.Z

    def active_move(self):
        if self.is_life and len(self.move_modes) > 1:
            self.move_switch_timer += 1
            if self.move_switch_timer >= 100:
                self.move_switch_timer = 0
                self.move_idx = random.randrange(len(self.move_modes))
        return self.move_modes[self.move_idx]

    def _clamp_bounds(self):
        l, r = PANEL_W + 10, WIDTH - 10
        if self.x < l: self.x, self.vx = l, abs(int(self.vx))
        if self.x > r: self.x, self.vx = r, -abs(int(self.vx))
        if self.y < 10: self.y, self.vy = 10, abs(int(self.vy))
        if self.y > HEIGHT - 10: self.y, self.vy = HEIGHT - 10, -abs(int(self.vy))

    def draw(self, surface):
        if not self.alive:
            return
        pos = (int(self.x), int(self.y))
        r = int(self.radius)
        if self.stable:
            pygame.draw.circle(surface, self.color, pos, r)
            pygame.draw.circle(surface, (220, 225, 235), pos, r, 2)
            lbl = FONT_XS.render(str(self.Z), True, (240, 240, 250))
            surface.blit(lbl, (pos[0] - len(str(self.Z)) * 3, pos[1] - 6))
            return
        pygame.draw.circle(surface, self.color, pos, r)
        if self.Z <= 3:
            pygame.draw.circle(surface, (255, 255, 255), pos, r, 2)
        if self.unrest:
            pygame.draw.circle(surface, (255, 90, 90), pos, r + 4, 1)
        if self.alt_phase == 2:
            pygame.draw.circle(surface, (180, 100, 255), pos, r + 2, 1)
        if self.is_life:
            pygame.draw.circle(surface, (255, 255, 180), pos, r + 3, 2)
        surface.blit(FONT_XS.render(str(self.Z), True, (20, 20, 30)), (pos[0] - 4, pos[1] - 6))

    def snapshot(self):
        return {
            "Z": self.Z, "D": self.D, "S": self.S,
            "color": self.color, "is_life": self.is_life,
            "move_modes": list(self.move_modes),
            "mother_zs": list(self.mother_zs),
            "move_idx": self.move_idx,
            "stable": self.stable,
        }

    @staticmethod
    def from_snapshot(snap, x, y):
        if snap.get("is_life"):
            p = Particle(0, x, y, life_data={
                "Z": snap["Z"], "D": snap["D"], "S": snap["S"],
                "x": x, "y": y, "color": snap["color"],
                "move_modes": list(snap["move_modes"]),
                "mother_zs": list(snap.get("mother_zs", [])),
            })
        else:
            p = Particle(int(snap["Z"]), x, y)
            p.D, p.S = int(snap["D"]), int(snap["S"])
            p.is_life = bool(snap.get("is_life", False))
            if snap.get("move_modes"):
                p.move_modes = list(snap["move_modes"])
            if snap.get("mother_zs"):
                p.mother_zs = list(snap["mother_zs"])
            if snap.get("color"):
                p.color = snap["color"]
        p.vx = p.vy = 0
        p.apply_state()
        return p

    def draw_mini(self, surface, cx, cy):
        r = max(6, min(10, int(self.radius * 0.55)))
        pygame.draw.circle(surface, self.color, (cx, cy), r)
        if self.stable:
            pygame.draw.circle(surface, (220, 225, 235), (cx, cy), r, 1)
        if self.is_life:
            pygame.draw.circle(surface, (255, 255, 180), (cx, cy), r + 1, 1)
        lbl = FONT_XS.render(str(self.Z), True, (240, 240, 250))
        surface.blit(lbl, (cx - 4, cy - 5))


class CollisionManager:
    """重叠期间每对粒子只触发一次碰撞，分离后冷却解除"""
    def __init__(self):
        self._locked = set()

    @staticmethod
    def _key(a, b):
        ia, ib = a.uid, b.uid
        return (ia, ib) if ia < ib else (ib, ia)

    def try_collide(self, a, b):
        key = self._key(a, b)
        dist = math.hypot(a.x - b.x, a.y - b.y)
        reach = a.radius + b.radius
        if a.unrest or b.unrest:
            reach = int(reach * 14 // 10)
        if dist >= reach:
            self._locked.discard(key)
            return False
        if key in self._locked:
            return False
        self._locked.add(key)
        return True


class ArchiveVault:
    """可拖动存档区 — 静止保存粒子，拖出时一比一复制"""
    SLOT = 36
    COLS = 4

    def __init__(self):
        self.rect = pygame.Rect(WIDTH - VAULT_W - 12, HEIGHT - VAULT_H - 12, VAULT_W, VAULT_H)
        self.snapshots = []
        self.dragging_vault = False
        self.drag_offset = (0, 0)
        self.drag_out_idx = None
        self.hover_idx = None

    def title_rect(self):
        return pygame.Rect(self.rect.x, self.rect.y, self.rect.w, 22)

    def content_rect(self):
        return pygame.Rect(self.rect.x + 6, self.rect.y + 26, self.rect.w - 12, self.rect.h - 32)

    def slot_at(self, mx, my):
        cr = self.content_rect()
        if not cr.collidepoint(mx, my):
            return None
        col = (mx - cr.x) // self.SLOT
        row = (my - cr.y) // self.SLOT
        idx = row * self.COLS + col
        if 0 <= idx < len(self.snapshots):
            return idx
        return None

    def contains(self, mx, my):
        return self.rect.collidepoint(mx, my)

    def archive_particle(self, p):
        self.snapshots.append(p.snapshot())

    def copy_out(self, idx, x, y):
        if 0 <= idx < len(self.snapshots):
            return Particle.from_snapshot(self.snapshots[idx], x, y)
        return None

    def handle_down(self, mx, my, button=1):
        if button != 1:
            return "none"
        if self.title_rect().collidepoint(mx, my):
            self.dragging_vault = True
            self.drag_offset = (mx - self.rect.x, my - self.rect.y)
            return "vault_move"
        idx = self.slot_at(mx, my)
        if idx is not None:
            self.drag_out_idx = idx
            return "vault_out"
        return "none"

    def handle_up(self, mx, my, particles):
        result = None
        if self.drag_out_idx is not None and in_canvas(mx, my):
            p = self.copy_out(self.drag_out_idx, *clamp_canvas(mx, my))
            if p:
                particles.append(p)
                result = "spawned"
        self.dragging_vault = False
        self.drag_out_idx = None
        return result

    def update_hover(self, mx, my):
        self.hover_idx = self.slot_at(mx, my)

    def move_vault(self, mx, my):
        if self.dragging_vault:
            nx = max(PANEL_W + 4, min(WIDTH - self.rect.w - 4, mx - self.drag_offset[0]))
            ny = max(4, min(HEIGHT - self.rect.h - 4, my - self.drag_offset[1]))
            self.rect.x, self.rect.y = nx, ny

    def draw(self, surface, mx, my):
        pygame.draw.rect(surface, (18, 20, 28), self.rect, border_radius=6)
        pygame.draw.rect(surface, (70, 80, 110), self.rect, 2, border_radius=6)
        tr = self.title_rect()
        pygame.draw.rect(surface, (30, 34, 48), tr)
        pygame.draw.line(surface, (55, 60, 80), (tr.x, tr.bottom), (tr.right, tr.bottom))
        surface.blit(FONT_XS.render(f"存档区 ({len(self.snapshots)})", True, (200, 205, 220)),
                     (tr.x + 8, tr.y + 5))
        surface.blit(FONT_XS.render("拖入存入/拖出复制", True, (120, 125, 140)), (tr.x + 90, tr.y + 5))
        cr = self.content_rect()
        pygame.draw.rect(surface, (24, 26, 34), cr, border_radius=4)
        for i, snap in enumerate(self.snapshots):
            row, col = divmod(i, self.COLS)
            cx = cr.x + col * self.SLOT + self.SLOT // 2
            cy = cr.y + row * self.SLOT + self.SLOT // 2
            if i == self.hover_idx:
                pygame.draw.rect(surface, (50, 55, 75), (cr.x + col * self.SLOT, cr.y + row * self.SLOT,
                                                         self.SLOT, self.SLOT), border_radius=3)
            tmp = Particle.from_snapshot(snap, cx, cy)
            tmp.draw_mini(surface, cx, cy)
        if self.drag_out_idx is not None and 0 <= self.drag_out_idx < len(self.snapshots):
            tmp = Particle.from_snapshot(self.snapshots[self.drag_out_idx], mx, my)
            tmp.draw_mini(surface, mx, my)
            surface.blit(FONT_XS.render("复制放置", True, (255, 230, 150)), (mx + 12, my - 8))


class SpeedInput:
    """时间速度数值输入框"""
    def __init__(self, y, w=PANEL_W - 16):
        self.rect = pygame.Rect(8, y, w, 24)
        self.text = "1.0"
        self.active = False
        self._blink = 0

    def get_value(self):
        try:
            return max(0.1, min(10.0, float(self.text)))
        except ValueError:
            return 1.0

    def handle_event(self, event, mx, my):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(mx, my)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.active = False
                v = self.get_value()
                self.text = f"{v:.1f}"
            elif event.key == pygame.K_ESCAPE:
                self.active = False
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.unicode in "0123456789." and len(self.text) < 6:
                if event.unicode == "." and "." in self.text:
                    return
                self.text += event.unicode

    def draw(self, surface):
        self._blink += 1
        bg = (45, 50, 65) if self.active else (32, 34, 42)
        pygame.draw.rect(surface, bg, self.rect, border_radius=3)
        pygame.draw.rect(surface, (100, 110, 140) if self.active else (60, 65, 80),
                         self.rect, 1, border_radius=3)
        label = FONT_XS.render("时间速度", True, (160, 165, 180))
        surface.blit(label, (self.rect.x, self.rect.y - 14))
        txt = self.text + ("|" if self.active and self._blink % 60 < 30 else "")
        surface.blit(FONT_XS.render(txt + "x", True, (230, 230, 240)), (self.rect.x + 6, self.rect.y + 5))


def draw_panel(selected_z, time_speed, speed_input, hovered, count, stats):
    pygame.draw.rect(screen, (22, 22, 28), (0, 0, PANEL_W, HEIGHT))
    pygame.draw.line(screen, (60, 60, 70), (PANEL_W, 0), (PANEL_W, HEIGHT), 2)
    screen.blit(FONT_LG.render("序列 Z", True, (220, 220, 220)), (12, 10))
    btn_h = 26
    for i in range(10):
        z = i + 1
        rect = pygame.Rect(8, 38 + i * (btn_h + 3), PANEL_W - 16, btn_h)
        pygame.draw.rect(screen, PARTICLE_DATA[i]["color"], rect, border_radius=3)
        if z == selected_z:
            pygame.draw.rect(screen, (255, 255, 80), rect, 2, border_radius=3)
        screen.blit(FONT_XS.render(f"Z{z} {PARTICLE_DATA[i]['name']}", True, (25, 25, 30)),
                    (rect.x + 4, rect.y + 6))
    y = 38 + 10 * (btn_h + 3) + 8
    speed_input.rect.y = y
    speed_input.draw(screen)
    y += 34
    for line in [f"粒子:{count}", f"稳态:{stats['stable']}", f"生命:{stats['life']}",
                 f"存档:{stats.get('archived', 0)}", "Enter确认速度", "[ ]微调",
                 "拖粒子→存档区存入"]:
        screen.blit(FONT_XS.render(line, True, (150, 150, 165)), (8, y))
        y += 16
    if hovered and hovered.alive:
        box_y = HEIGHT - 145
        pygame.draw.rect(screen, (35, 35, 48), (5, box_y, PANEL_W - 10, 135), border_radius=4)
        bc = alternate_broadcast(hovered.Z, hovered.D, hovered.S)
        rc = alternate_receive(hovered.Z, hovered.D, hovered.S)
        sc = behavior_scale(hovered.D, hovered.S)
        lines = [
            f"序Z={hovered.Z}{'稳' if hovered.stable else ''} 幅={sc}",
            f"电D={hovered.D}",
            f"时S={hovered.S}",
            f"阶段={hovered.alt_phase} 共振={hovered.alt_resonance}",
            f"播={bc}",
            f"收={rc}",
            f"移={hovered.active_move()}",
        ]
        for i, ln in enumerate(lines):
            screen.blit(FONT_XS.render(ln, True, (195, 195, 210)), (10, box_y + 6 + i * 16))


def panel_z_at(mx, my):
    btn_h = 26
    for i in range(10):
        rect = pygame.Rect(8, 38 + i * (btn_h + 3), PANEL_W - 16, btn_h)
        if rect.collidepoint(mx, my):
            return i + 1
    return None


def find_particle_at(particles, mx, my):
    for p in reversed(particles):
        if p.alive and math.hypot(p.x - mx, p.y - my) < p.radius + 6:
            return p
    return None


def run_sim_step(particles, time_speed, collision_mgr):
    for p in particles:
        if p.alive:
            p.unrest = False
            p.alt_phase = p.alt_resonance = 0
            time_func(p, particles)

    unrest, _, life_pairs = alternate_apply_phases(particles)
    for p in unrest:
        p.unrest = True

    for p in particles:
        if p.alive:
            move_func(p, particles, WIND, time_speed)

    alive = [p for p in particles if p.alive]
    for i in range(len(alive)):
        for j in range(i + 1, len(alive)):
            a, b = alive[i], alive[j]
            if collision_mgr.try_collide(a, b):
                collision_func(a, b)

    for p in particles:
        if p.alive and not p.stable:
            special_check_func(p, particles)

    merged = set()
    new_life = []
    for a, b in life_pairs:
        if id(a) in merged or id(b) in merged or not a.alive or not b.alive:
            continue
        data = life_spawn_calc(a, b)
        if data:
            merged |= {id(a), id(b)}
            a.alive = b.alive = False
            new_life.append(Particle(0, life_data=data))
    particles.extend(new_life)
    particles[:] = [p for p in particles if p.alive]


def main():
    particles = []
    selected_z = 1
    speed_input = SpeedInput(360)
    vault = ArchiveVault()
    collision_mgr = CollisionManager()
    dragging = spawn_drag = None
    time_accum = 0.0

    while True:
        screen.fill((28, 28, 32))
        mx, my = pygame.mouse.get_pos()
        hovered = find_particle_at(particles, mx, my) if in_canvas(mx, my) else None
        time_speed = speed_input.get_value()
        vault.update_hover(mx, my)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            speed_input.handle_event(event, mx, my)
            if event.type == pygame.KEYDOWN:
                if speed_input.active:
                    continue
                if event.key == pygame.K_c:
                    particles.clear()
                elif event.key == pygame.K_LEFTBRACKET:
                    ts = max(0.1, time_speed - 0.1)
                    speed_input.text = f"{ts:.1f}"
                elif event.key == pygame.K_RIGHTBRACKET:
                    ts = min(10.0, time_speed + 0.1)
                    speed_input.text = f"{ts:.1f}"
                elif pygame.K_1 <= event.key <= pygame.K_9:
                    selected_z = event.key - pygame.K_0
                elif event.key == pygame.K_0:
                    selected_z = 10
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if vault.handle_down(mx, my) != "none":
                    pass
                elif mx < PANEL_W:
                    if not speed_input.rect.collidepoint(mx, my):
                        z = panel_z_at(mx, my)
                        if z:
                            selected_z = z
                elif in_canvas(mx, my) and not vault.contains(mx, my):
                    hit = find_particle_at(particles, mx, my)
                    dragging = hit if hit else None
                    if not hit:
                        spawn_drag = (mx, my)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if vault.drag_out_idx is not None:
                    vault.handle_up(mx, my, particles)
                elif dragging and vault.contains(mx, my):
                    vault.archive_particle(dragging)
                    particles.remove(dragging)
                elif spawn_drag and in_canvas(mx, my) and not vault.contains(mx, my):
                    particles.append(Particle(selected_z, *clamp_canvas(mx, my)))
                spawn_drag = None
                dragging = None
                vault.dragging_vault = False

        vault.move_vault(mx, my)
        if dragging and not vault.drag_out_idx:
            dragging.x, dragging.y = clamp_canvas(*pygame.mouse.get_pos())
        if spawn_drag and in_canvas(mx, my):
            pygame.draw.circle(screen, PARTICLE_DATA[selected_z - 1]["color"] + (100,),
                               (mx, my), 12, 2)

        time_accum += time_speed
        sim_steps = int(time_accum)
        if sim_steps > 0:
            time_accum -= sim_steps
            for _ in range(sim_steps):
                run_sim_step(particles, time_speed, collision_mgr)

        pygame.draw.rect(screen, (24, 24, 28), (PANEL_W, 0, CANVAS_W, HEIGHT))
        for p in particles:
            p.draw(screen)
        vault.draw(screen, mx, my)
        stats = {"stable": sum(1 for p in particles if p.stable),
                 "life": sum(1 for p in particles if p.is_life),
                 "archived": len(vault.snapshots)}
        draw_panel(selected_z, time_speed, speed_input, hovered or dragging, len(particles), stats)
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
