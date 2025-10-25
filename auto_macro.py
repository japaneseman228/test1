import sys
from pathlib import Path

def get_templates_dir():
    # Если приложение упаковано PyInstaller, ресурсы доступны в _MEIPASS
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        templates = base / "templates"
    else:
        # запускается как скрипт — ищем templates рядом с файлом
        base = Path(__file__).parent
        templates = base / "templates"
    return templates

# потом в коде использовать:
TEMPLATES_DIR = get_templates_dir()
"""
auto_macro.py

Авто-макро для локальной (fan) версии игры.
Toggle Start/Stop: F6

Требования:
pip install opencv-python numpy pillow pyautogui keyboard
"""

import time
import threading
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import pyautogui
import keyboard  # слушатель горячих клавиш

# ========== КОНФИГУРАЦИЯ ==========
TEMPLATES_DIR = Path("templates")  # содержит M1.png, M2.png, WAIT.png

# Область захвата — относительная от центра (в пикселях)
CAP_WIDTH = 520   # ширина полосы где лежат 4 иконки
CAP_HEIGHT = 100  # высота полосы
# Если иконки выше/ниже центра, скорректируй вертикальный сдвиг (положительный — вниз)
VERTICAL_SHIFT = -50

# Пороги совпадения шаблона (0..1). Подбери экспериментально
MATCH_THRESHOLD = 0.62

# Тайминги (сек)
HOLD_E = 0.05     # "нажатие" E
HOLD_1 = 0.05
CLICK_INTERVAL = 0.05
HOLD_R = 0.05
WAIT_AFTER_DETECT = 6.0       # пункт 5: ожидание 6 секунд (в это время делаем распознавание)
WAIT_FOR_WAIT_ICON = 2.3      # WAIT => ожидание 2.3 сек
LOOP_DELAY = 0.2              # пауза между итерациями основного цикла

# Настройки кликов
CLICK_POS = None  # None = клик в текущей позиции мыши (как просил "без наводки")
# ========== КОНЕЦ КОНФИГУРАЦИИ ==========

# Глобальная переменная состояния
running = False
stop_event = threading.Event()

def load_templates():
    templates = {}
    for name in ("M1", "M2", "WAIT"):
        p = TEMPLATES_DIR / f"{name}.png"
        if not p.exists():
            raise FileNotFoundError(f"Template missing: {p}")
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Can't read template: {p}")
        templates[name] = img
    return templates

def grab_center_strip(width, height, vshift=0):
    screen_w, screen_h = pyautogui.size()
    cx = screen_w // 2
    cy = screen_h // 2 + vshift
    left = max(cx - width // 2, 0)
    top = max(cy - height // 2, 0)
    # pyautogui.screenshot returns PIL Image
    img = pyautogui.screenshot(region=(left, top, width, height))
    frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    return frame, (left, top)

def recognize_four_icons(frame_gray, templates):
    """
    Разбиваем полосу frame_gray на 4 равные области слева->право и для каждой пытаемся определить шаблон.
    Возвращаем список длины 4, элементы 'M1'/'M2'/'WAIT' или 'UNKNOWN'
    """
    h, w = frame_gray.shape
    icon_w = w // 4
    results = []
    for i in range(4):
        x1 = i * icon_w
        x2 = (i + 1) * icon_w if i < 3 else w
        sub = frame_gray[:, x1:x2]
        best_name = "UNKNOWN"
        best_score = -1.0
        for name, tmpl in templates.items():
            # масштабируем шаблон если оно больше субобласти
            th, tw = tmpl.shape
            if th > sub.shape[0] or tw > sub.shape[1]:
                # если шаблон больше, уменьшим шаблон (линейная интерполяция)
                scale = min(sub.shape[0] / th, sub.shape[1] / tw)
                new_size = (max(1, int(tw*scale)), max(1, int(th*scale)))
                tmpl_resized = cv2.resize(tmpl, new_size, interpolation=cv2.INTER_AREA)
            else:
                tmpl_resized = tmpl
            res = cv2.matchTemplate(sub, tmpl_resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = max_val
                best_name = name
        # Проверяем порог
        if best_score >= MATCH_THRESHOLD:
            results.append(best_name)
        else:
            # Если ниже порога, можно считать как WAIT для устойчивости, но я ставлю UNKNOWN
            results.append("UNKNOWN")
    return results

# ========== Действия: нажатия и клики ==========
def press_key(key, hold=0.05):
    pyautogui.keyDown(key)
    time.sleep(hold)
    pyautogui.keyUp(key)

def click_lmb():
    if CLICK_POS:
        pyautogui.click(CLICK_POS[0], CLICK_POS[1], button='left')
    else:
        pyautogui.click(button='left')

def click_rmb():
    if CLICK_POS:
        pyautogui.click(CLICK_POS[0], CLICK_POS[1], button='right')
    else:
        pyautogui.click(button='right')
# ==========

def execute_sequence_from_icons(icon_list):
    """
    icon_list: ['M1','WAIT','M2','M1'] и т.д.
    Выполняем слева->направо
    """
    for idx, it in enumerate(icon_list):
        if stop_event.is_set():
            return
        if it == "M1":
            click_lmb()
            time.sleep(CLICK_INTERVAL)
        elif it == "M2":
            click_rmb()
            time.sleep(CLICK_INTERVAL)
        elif it == "WAIT":
            time.sleep(WAIT_FOR_WAIT_ICON)
        elif it == "UNKNOWN":
            # если не распознали — делаем короткое ожидание
            time.sleep(0.12)
        else:
            time.sleep(0.1)

def one_full_cycle(templates):
    # 1) нажать E
    press_key('e', HOLD_E)
    time.sleep(0.05)
    # 2) нажать 1 (не numpad)
    press_key('1', HOLD_1)
    time.sleep(0.05)
    # 3) клик ЛКМ
    click_lmb()
    time.sleep(0.05)
    # 4) нажать R
    press_key('r', HOLD_R)

    # пункты 5-10: 3 раза: ждать 6s (в это время распознаём) -> выполнять
    for pass_i in range(3):
        if stop_event.is_set():
            return
        # Ждём 6 секунд, но распознаём в начале (чтобы не тратить весь тайм)
        # Делать распознавание в самом начале ожидания (в скриншоте будет показано текущее)
        frame, (left, top) = grab_center_strip(CAP_WIDTH, CAP_HEIGHT, VERTICAL_SHIFT)
        icons = recognize_four_icons(frame, templates)
        # можно вывести в лог
        print(f"[pass {pass_i+1}] recognized: {icons}")
        # Ждём (оставшееся от 6 секунд). Здесь делаем параллель: распознали и ждём
        t0 = time.time()
        while time.time() - t0 < WAIT_AFTER_DETECT:
            if stop_event.is_set():
                return
            time.sleep(0.05)
        # После ожидания выполняем действия слева->направо
        execute_sequence_from_icons(icons)
    # 11) нажать R
    press_key('r', HOLD_R)

def worker_loop():
    global running
    templates = load_templates()
    print("Templates loaded. Waiting for F6 to start/stop.")
    while True:
        if stop_event.is_set():
            print("Stop event set; exiting worker loop.")
            return
        if running:
            try:
                one_full_cycle(templates)
            except Exception as e:
                print("Error in cycle:", e)
            time.sleep(LOOP_DELAY)
        else:
            time.sleep(0.2)

# Горячая клавиша F6 — toggle
def on_toggle():
    global running, stop_event
    running = not running
    print("Running ->", running)
    if not running:
        # если остановка — уведомляем worker прекратить текущую активность
        stop_event.set()
        # очистим флаг и создадим новый для следующего запуска
        stop_event.clear()

def main():
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    # Регистрируем F6
    keyboard.add_hotkey('f6', lambda: on_toggle())
    print("Press F6 to toggle Start/Stop. Press Esc to quit.")
    # Для выхода — Esc
    keyboard.wait('esc')
    print("Exiting...")
    # при выходе выставляем stop
    stop_event.set()
    time.sleep(0.3)

if __name__ == "__main__":
    main()
