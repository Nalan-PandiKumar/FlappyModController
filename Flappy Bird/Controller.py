import ctypes
import time
import threading
import subprocess
import sys
import os
import frida
import struct

from ctypes import wintypes


# ============================================================
# CONFIGURATION
# ============================================================

GAME_EXE = "FlappyBird.exe"

CUSTOM_SPEED = 5

# Global Game* variable RVA
GAME_POINTER_RVA = 0x18A948

# Game structure offsets
PLAYER_Y_OFFSET = 0
PLAYER_VELOCITY_OFFSET = 4
SCORE_OFFSET = 68
PIPE_SPEED_OFFSET = 72
GAME_OVER_OFFSET = 76

# Function RVAs
CHECK_COLLISION_RVA = 0x10F90
UPDATE_DIFFICULTY_RVA = 0x10F50

# Autopilot
PLAYER_X = 10
AUTOPILOT_INTERVAL = 0.08


# ============================================================
# WINDOWS API
# ============================================================

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


# ------------------------------------------------------------
# Toolhelp constants
# ------------------------------------------------------------

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

PROCESS_ALL_ACCESS = 0x1F0FFF

# Wait / process constants
SYNCHRONIZE = 0x00100000
INFINITE = 0xFFFFFFFF


# ------------------------------------------------------------
# PROCESSENTRY32
# ------------------------------------------------------------

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


# ------------------------------------------------------------
# MODULEENTRY32
# ------------------------------------------------------------

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_ubyte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260),
    ]


# ------------------------------------------------------------
# Function prototypes
# ------------------------------------------------------------

kernel32.CreateToolhelp32Snapshot.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD
]

kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE


kernel32.Process32First.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(PROCESSENTRY32)
]

kernel32.Process32First.restype = wintypes.BOOL


kernel32.Process32Next.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(PROCESSENTRY32)
]

kernel32.Process32Next.restype = wintypes.BOOL


kernel32.Module32First.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(MODULEENTRY32)
]

kernel32.Module32First.restype = wintypes.BOOL


kernel32.Module32Next.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(MODULEENTRY32)
]

kernel32.Module32Next.restype = wintypes.BOOL


kernel32.OpenProcess.argtypes = [
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD
]

kernel32.OpenProcess.restype = wintypes.HANDLE


kernel32.CloseHandle.argtypes = [
    wintypes.HANDLE
]

kernel32.CloseHandle.restype = wintypes.BOOL


kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t)
]

kernel32.ReadProcessMemory.restype = wintypes.BOOL


kernel32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.LPCVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t)
]

kernel32.WriteProcessMemory.restype = wintypes.BOOL


kernel32.WaitForSingleObject.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD
]

kernel32.WaitForSingleObject.restype = wintypes.DWORD


# ============================================================
# PROCESS HELPERS
# ============================================================

def find_process():
    """
    Find the first flappy-1.exe process.
    Returns PID or None.
    """

    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPPROCESS,
        0
    )

    if snapshot == wintypes.HANDLE(-1).value:
        return None

    try:

        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)

        if not kernel32.Process32First(
            snapshot,
            ctypes.byref(entry)
        ):
            return None

        while True:

            try:
                exe_name = entry.szExeFile.decode(
                    "utf-8",
                    errors="ignore"
                )
            except Exception:
                exe_name = ""

            if exe_name.lower() == GAME_EXE.lower():
                return entry.th32ProcessID

            if not kernel32.Process32Next(
                snapshot,
                ctypes.byref(entry)
            ):
                break

    finally:

        kernel32.CloseHandle(snapshot)

    return None


def find_module(pid):
    """
    Find flappy-1.exe module base for a specific PID.
    Returns module base address or None.
    """

    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
        pid
    )

    if snapshot == wintypes.HANDLE(-1).value:
        return None

    try:

        module = MODULEENTRY32()
        module.dwSize = ctypes.sizeof(MODULEENTRY32)

        if not kernel32.Module32First(
            snapshot,
            ctypes.byref(module)
        ):
            return None

        while True:

            try:
                module_name = module.szModule.decode(
                    "utf-8",
                    errors="ignore"
                )
            except Exception:
                module_name = ""

            if module_name.lower() == GAME_EXE.lower():

                return ctypes.cast(
                    module.modBaseAddr,
                    ctypes.c_void_p
                ).value

            if not kernel32.Module32Next(
                snapshot,
                ctypes.byref(module)
            ):
                break

    finally:

        kernel32.CloseHandle(snapshot)

    return None


def open_process(pid):

    return kernel32.OpenProcess(
        PROCESS_ALL_ACCESS,
        False,
        pid
    )


def process_is_alive(process_handle):

    if not process_handle:
        return False

    result = kernel32.WaitForSingleObject(
        process_handle,
        0
    )

    return result == 0x00000102  # WAIT_TIMEOUT


# ============================================================
# MEMORY FUNCTIONS
# ============================================================

def read_memory(process_handle, address, size):

    buffer = (ctypes.c_ubyte * size)()
    bytes_read = ctypes.c_size_t()

    success = kernel32.ReadProcessMemory(
        process_handle,
        ctypes.c_void_p(address),
        buffer,
        size,
        ctypes.byref(bytes_read)
    )

    if not success or bytes_read.value != size:
        return None

    return bytes(buffer)


def write_memory(process_handle, address, data):

    buffer = ctypes.create_string_buffer(data)
    bytes_written = ctypes.c_size_t()

    success = kernel32.WriteProcessMemory(
        process_handle,
        ctypes.c_void_p(address),
        buffer,
        len(data),
        ctypes.byref(bytes_written)
    )

    return (
        bool(success)
        and bytes_written.value == len(data)
    )


def read_int32(process_handle, address):

    data = read_memory(
        process_handle,
        address,
        4
    )

    if data is None:
        return None

    return int.from_bytes(
        data,
        byteorder="little",
        signed=True
    )


def read_uint8(process_handle, address):

    data = read_memory(
        process_handle,
        address,
        1
    )

    if data is None:
        return None

    return data[0]


def read_uint64(process_handle, address):

    data = read_memory(
        process_handle,
        address,
        8
    )

    if data is None:
        return None

    return int.from_bytes(
        data,
        byteorder="little",
        signed=False
    )


def write_int32(process_handle, address, value):

    data = int(value).to_bytes(
        4,
        byteorder="little",
        signed=True
    )

    return write_memory(
        process_handle,
        address,
        data
    )


# ============================================================
# GAME POINTER
# ============================================================

def get_game_address(
    process_handle,
    module_base
):
    """
    module_base + GAME_POINTER_RVA
        ↓
    global Game* variable
        ↓
    actual Game object
    """

    pointer_location = (
        module_base +
        GAME_POINTER_RVA
    )

    game_address = read_uint64(
        process_handle,
        pointer_location
    )

    if not game_address:
        return None

    return game_address


# ============================================================
# WAIT FOR GAME
# ============================================================

def wait_for_game():

    print()
    print("┌──────────────────────────────────────┐")
    print("│ Waiting for FlappyBird.exe...        │")
    print("└──────────────────────────────────────┘")

    while True:

        pid = find_process()

        if pid is not None:
            break

        time.sleep(0.5)

    print()
    print(
        f"[Controller] Game detected (PID: {pid})"
    )

    process_handle = open_process(pid)

    if not process_handle:

        print(
            "[Controller] Failed to open process."
        )

        return None

    module_base = None

    for _ in range(20):

        module_base = find_module(pid)

        if module_base is not None:
            break

        time.sleep(0.1)

    if module_base is None:

        print(
            "[Controller] Failed to find module."
        )

        kernel32.CloseHandle(process_handle)

        return None

    print(
        f"[Controller] Module Base : "
        f"0x{module_base:X}"
    )

    game_address = None

    for _ in range(20):

        game_address = get_game_address(
            process_handle,
            module_base
        )

        if game_address is not None:
            break

        time.sleep(0.1)

    if game_address is None:

        print(
            "[Controller] Failed to resolve Game*."
        )

        kernel32.CloseHandle(process_handle)

        return None

    print(
        f"[Controller] Game*        : "
        f"0x{game_address:X}"
    )

    return (
        pid,
        module_base,
        game_address,
        process_handle
    )


# ============================================================
# GOD MODE FREEZE
# ============================================================

def freeze_player(
    process_handle,
    game_address,
    stop_event,
    frozen_y
):

    y_address = (
        game_address +
        PLAYER_Y_OFFSET
    )

    velocity_address = (
        game_address +
        PLAYER_VELOCITY_OFFSET
    )

    while not stop_event.is_set():

        write_int32(
            process_handle,
            y_address,
            frozen_y
        )

        write_int32(
            process_handle,
            velocity_address,
            0
        )

        stop_event.wait(0.01)


# ============================================================
# AUTOPILOT
# ============================================================

def read_game_struct(
    process_handle,
    game
):

    buffer = ctypes.create_string_buffer(80)
    read = ctypes.c_size_t()

    ok = kernel32.ReadProcessMemory(
        process_handle,
        ctypes.c_void_p(game),
        buffer,
        80,
        ctypes.byref(read)
    )

    if not ok or read.value != 80:
        return None

    data = buffer.raw

    player_y, velocity = struct.unpack_from(
        "<ii",
        data,
        0
    )

    pipes = []

    for i in range(3):

        offset = 8 + i * 20

        x, gap_y, gap_size, width = (
            struct.unpack_from(
                "<iiii",
                data,
                offset
            )
        )

        passed = struct.unpack_from(
            "<?",
            data,
            offset + 16
        )[0]

        pipes.append({
            "x": x,
            "gapY": gap_y,
            "gapSize": gap_size,
            "width": width,
            "passed": passed
        })

    score, pipe_speed = struct.unpack_from(
        "<ii",
        data,
        68
    )

    game_over = struct.unpack_from(
        "<?",
        data,
        76
    )[0]

    return {
        "player_y": player_y,
        "velocity": velocity,
        "pipes": pipes,
        "score": score,
        "pipe_speed": pipe_speed,
        "game_over": game_over
    }


def jump(
    process_handle,
    game
):

    velocity_address = game + 4

    value = ctypes.c_int32(-3)
    written = ctypes.c_size_t()

    kernel32.WriteProcessMemory(
        process_handle,
        ctypes.c_void_p(velocity_address),
        ctypes.byref(value),
        4,
        ctypes.byref(written)
    )


def autopilot_loop(
    process_handle,
    game_address,
    stop_event
):

    print()
    print("[AUTO PILOT ACTIVE]")
    print()

    while not stop_event.is_set():

        state = read_game_struct(
            process_handle,
            game_address
        )

        if not state:
            break

        if state["game_over"]:

            print(
                f"\n[Auto Pilot] GAME OVER!"
                f"\n[Auto Pilot] Final Score: "
                f"{state['score']}"
            )

            break

        player_y = state["player_y"]
        velocity = state["velocity"]

        pipes = state["pipes"]

        target_pipe = None

        for pipe in pipes:

            if pipe["x"] + pipe["width"] >= PLAYER_X:

                if (
                    target_pipe is None
                    or pipe["x"] < target_pipe["x"]
                ):

                    target_pipe = pipe

        if target_pipe:

            gap_top = target_pipe["gapY"]

            gap_bottom = (
                gap_top +
                target_pipe["gapSize"]
            )

            target_y = (
                gap_top +
                target_pipe["gapSize"] // 2
            )

            if velocity >= 0:

                if (
                    player_y >= target_y
                    or
                    player_y + velocity
                    >= gap_bottom - 2
                ):

                    jump(
                        process_handle,
                        game_address
                    )

        stop_event.wait(
            AUTOPILOT_INTERVAL
        )

    print("[Auto Pilot] Stopped.")


# ============================================================
# FRIDA HOOKS
# ============================================================

def install_frida_hooks(
    pid,
    module_base,
    game_address,
    mode
):

    session = frida.attach(pid)

    script_parts = []

    # --------------------------------------------------------
    # GOD MODE
    # --------------------------------------------------------

    if mode in (
        "God Mode",
        "God Mode + Speed Control"
    ):

        check_collision_address = (
            module_base +
            CHECK_COLLISION_RVA
        )

        god_hook = f"""
        const checkCollision =
            ptr("0x{check_collision_address:X}");

        Interceptor.attach(checkCollision, {{

            onLeave(retval) {{

                retval.replace(0);
            }}
        }});

        send({{
            type: "god_installed"
        }});
        """

        script_parts.append(god_hook)

    # --------------------------------------------------------
    # SPEED CONTROL
    # --------------------------------------------------------

    if mode in (
        "Speed Control",
        "God Mode + Speed Control"
    ):

        update_difficulty_address = (
            module_base +
            UPDATE_DIFFICULTY_RVA
        )

        pipe_speed_address = (
            game_address +
            PIPE_SPEED_OFFSET
        )

        speed_hook = f"""
        const updateDifficulty =
            ptr("0x{update_difficulty_address:X}");

        const pipeSpeed =
            ptr("0x{pipe_speed_address:X}");

        Interceptor.attach(updateDifficulty, {{

            onLeave() {{

                pipeSpeed.writeS32(
                    {CUSTOM_SPEED}
                );
            }}
        }});

        send({{
            type: "speed_installed"
        }});
        """

        script_parts.append(speed_hook)

    script_source = "\n".join(
        script_parts
    )

    script = session.create_script(
        script_source
    )

    def on_message(message, data):

        if message["type"] == "send":

            payload = message.get(
                "payload",
                {}
            )

            message_type = payload.get(
                "type"
            )

            if message_type == "god_installed":

                print(
                    "[Frida] God Mode hook installed"
                )

            elif message_type == "speed_installed":

                print(
                    "[Frida] Speed Control hook installed"
                )

        elif message["type"] == "error":

            print("[Frida Error]")

            print(
                message.get(
                    "stack",
                    message
                )
            )

    script.on(
        "message",
        on_message
    )

    script.load()

    return session


# ============================================================
# TELEMETRY
# ============================================================

def telemetry_process_main():

    """
    Child telemetry process.

    Usage:

        Controller.py --telemetry PID GAME_ADDRESS
    """

    if len(sys.argv) < 4:
        return

    try:

        pid = int(sys.argv[2])

        game_address = int(
            sys.argv[3],
            16
        )

    except ValueError:

        return

    process_handle = open_process(pid)

    if not process_handle:

        print(
            "[Telemetry] Failed to open game process."
        )

        return

    try:

        while process_is_alive(process_handle):

            # ------------------------------------------------
            # Read telemetry
            # ------------------------------------------------

            y = read_int32(
                process_handle,
                game_address +
                PLAYER_Y_OFFSET
            )

            velocity = read_int32(
                process_handle,
                game_address +
                PLAYER_VELOCITY_OFFSET
            )

            score = read_int32(
                process_handle,
                game_address +
                SCORE_OFFSET
            )

            pipe_speed = read_int32(
                process_handle,
                game_address +
                PIPE_SPEED_OFFSET
            )

            game_over = read_uint8(
                process_handle,
                game_address +
                GAME_OVER_OFFSET
            )

            # ------------------------------------------------
            # Format values
            # ------------------------------------------------

            y_text = (
                "N/A"
                if y is None
                else str(y)
            )

            velocity_text = (
                "N/A"
                if velocity is None
                else str(velocity)
            )

            score_text = (
                "N/A"
                if score is None
                else str(score)
            )

            speed_text = (
                "N/A"
                if pipe_speed is None
                else str(pipe_speed)
            )

            if game_over is None:

                status = "UNKNOWN"

            elif game_over != 0:

                status = "GAME OVER"

            else:

                status = "RUNNING"

            # ------------------------------------------------
            # Clear terminal
            # ------------------------------------------------

            os.system("cls")

            # ------------------------------------------------
            # Telemetry UI
            # ------------------------------------------------

            print(
                "╔══════════════════════════════════════════╗"
            )

            print(
                "║          FLAPPY LIVE TELEMETRY           ║"
            )

            print(
                "╠══════════════════════════════════════════╣"
            )

            print(
                f"║  PID          : {pid:<25}║"
            )

            print(
                f"║  Game Address : "
                f"0x{game_address:016X}{' ' * 7}║"
            )

            print(
                "║                                          ║"
            )

            print(
                f"║  Player Y     : {y_text:<25}║"
            )

            print(
                f"║  Velocity     : {velocity_text:<25}║"
            )

            print(
                f"║  Score        : {score_text:<25}║"
            )

            print(
                f"║  Pipe Speed   : {speed_text:<25}║"
            )

            print(
                "║                                          ║"
            )

            print(
                f"║  Status       : {status:<25}║"
            )

            print(
                "╚══════════════════════════════════════════╝"
            )

            time.sleep(0.1)

    finally:

        kernel32.CloseHandle(
            process_handle
        )


def start_telemetry_terminal(
    pid,
    game_address
):

    """
    Start telemetry in a separate console.
    """

    script_path = os.path.abspath(__file__)

    command = [
        sys.executable,
        script_path,
        "--telemetry",
        str(pid),
        f"{game_address:X}"
    ]

    startupinfo = subprocess.STARTUPINFO()

    startupinfo.dwFlags |= (
        subprocess.STARTF_USESHOWWINDOW
    )

    startupinfo.wShowWindow = 6

    try:

        process = subprocess.Popen(
            command,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            startupinfo=startupinfo
        )

        return process

    except Exception as e:

        print(
            "[Controller] Failed to start telemetry:"
        )

        print(
            f"  {type(e).__name__}: {e}"
        )

        return None


# ============================================================
# WAIT FOR SPECIFIC PID TO EXIT
# ============================================================

def wait_for_pid_exit(pid):

    """
    Wait until the exact PID we attached to disappears.
    """

    while True:

        current_pid = find_process()

        if current_pid != pid:
            return

        time.sleep(0.2)


# ============================================================
# RUN SELECTED MODE
# ============================================================

def run_selected_mode(mode):

    result = wait_for_game()

    if result is None:
        return

    (
        pid,
        module_base,
        game_address,
        process_handle
    ) = result

    freeze_thread = None
    freeze_stop_event = None

    autopilot_thread = None
    autopilot_stop_event = None

    frida_session = None
    telemetry_process = None

    try:

        # ====================================================
        # GOD MODE INITIALIZATION
        # ====================================================

        if mode in (
            "God Mode",
            "God Mode + Speed Control"
        ):

            current_y = read_int32(
                process_handle,
                game_address +
                PLAYER_Y_OFFSET
            )

            if (
                current_y is None
                or current_y < 0
                or current_y > 20
            ):

                current_y = 10

            print(
                f"[Controller] Freeze Y     : "
                f"{current_y}"
            )

            freeze_stop_event = threading.Event()

            freeze_thread = threading.Thread(
                target=freeze_player,
                args=(
                    process_handle,
                    game_address,
                    freeze_stop_event,
                    current_y
                ),
                daemon=True
            )

            freeze_thread.start()

        # ====================================================
        # FRIDA
        # ====================================================

        needs_frida = mode in (
            "God Mode",
            "Speed Control",
            "God Mode + Speed Control"
        )

        if needs_frida:

            print(
                "[Controller] Installing hooks..."
            )

            frida_session = install_frida_hooks(
                pid,
                module_base,
                game_address,
                mode
            )

        else:

            print(
                "[Controller] "
                "No Frida hooks required."
            )

        # ====================================================
        # SPEED CONTROL
        # ====================================================

        if mode in (
            "Speed Control",
            "God Mode + Speed Control"
        ):

            success = write_int32(
                process_handle,
                game_address +
                PIPE_SPEED_OFFSET,
                CUSTOM_SPEED
            )

            if success:

                print(
                    f"[Controller] Pipe Speed  : "
                    f"{CUSTOM_SPEED}"
                )

            else:

                print(
                    "[Controller] Failed to set "
                    "initial pipe speed."
                )

        # ====================================================
        # AUTOPILOT
        # ====================================================

        if mode == "Auto Pilot":

            autopilot_stop_event = (
                threading.Event()
            )

            autopilot_thread = threading.Thread(
                target=autopilot_loop,
                args=(
                    process_handle,
                    game_address,
                    autopilot_stop_event
                ),
                daemon=True
            )

            autopilot_thread.start()

        # ====================================================
        # TELEMETRY
        # ====================================================

        print(
            "[Controller] Starting telemetry..."
        )

        telemetry_process = (
            start_telemetry_terminal(
                pid,
                game_address
            )
        )

        if telemetry_process is not None:

            print(
                "[Controller] Telemetry terminal started."
            )

        print()

        print(
            "╔══════════════════════════════════════╗"
        )

        print(
            f"║ Mode : {mode:<30}║"
        )

        print(
            "║                                      ║"
        )

        print(
            "║ Telemetry : Separate terminal        ║"
        )

        print(
            "║ Status    : ACTIVE                   ║"
        )

        print(
            "╚══════════════════════════════════════╝"
        )

        print()

        print(
            "[Controller] Waiting for game to end..."
        )

        # ====================================================
        # WAIT FOR SAME PID
        # ====================================================

        wait_for_pid_exit(pid)

    except frida.ProcessNotFoundError:

        print(
            "[Controller] Process exited before "
            "Frida could attach."
        )

    except Exception as e:

        print()
        print(
            "[Controller] Error:"
        )

        print(
            f"  {type(e).__name__}: {e}"
        )

    finally:

        # ====================================================
        # STOP AUTOPILOT
        # ====================================================

        if autopilot_stop_event is not None:

            autopilot_stop_event.set()

        if autopilot_thread is not None:

            autopilot_thread.join(
                timeout=1.0
            )

        # ====================================================
        # STOP FREEZE THREAD
        # ====================================================

        if freeze_stop_event is not None:

            freeze_stop_event.set()

        if freeze_thread is not None:

            freeze_thread.join(
                timeout=1.0
            )

        # ====================================================
        # DETACH FRIDA
        # ====================================================

        if frida_session is not None:

            try:

                frida_session.detach()

            except Exception:

                pass

        # ====================================================
        # CLOSE TELEMETRY TERMINAL
        # ====================================================

        if telemetry_process is not None:

            try:

                if telemetry_process.poll() is None:

                    telemetry_process.terminate()

                    telemetry_process.wait(
                        timeout=2
                    )

            except Exception:

                pass

        # ====================================================
        # CLOSE PROCESS HANDLE
        # ====================================================

        if process_handle:

            try:

                kernel32.CloseHandle(
                    process_handle
                )

            except Exception:

                pass

        print()
        print(
            "[Controller] Game session ended."
        )

        print(
            "[Controller] Returning to menu..."
        )

        time.sleep(1)


# ============================================================
# MENU
# ============================================================

def show_menu():

    print()

    print(
        "╔══════════════════════════════════════╗"
    )

    print(
        "║        FLAPPY MOD CONTROLLER         ║"
    )

    print(
        "╠══════════════════════════════════════╣"
    )

    print(
        "║                                      ║"
    )

    print(
        "║  1. God Mode                         ║"
    )

    print(
        "║  2. Speed Control                    ║"
    )

    print(
        "║  3. God Mode + Speed Control         ║"
    )

    print(
        "║  4. Auto Pilot                       ║"
    )

    print(
        "║  5. Exit                             ║"
    )

    print(
        "║                                      ║"
    )

    print(
        "╚══════════════════════════════════════╝"
    )


# ============================================================
# CONTROLLER MAIN
# ============================================================

def controller_main():

    while True:

        show_menu()

        choice = input(
            "\nSelect mode: "
        ).strip()

        if choice == "1":

            mode = "God Mode"

        elif choice == "2":

            mode = "Speed Control"

        elif choice == "3":

            mode = "God Mode + Speed Control"

        elif choice == "4":

            mode = "Auto Pilot"

        elif choice == "5":

            print(
                "\n[Controller] Exiting..."
            )

            break

        else:

            print(
                "\n[Controller] Invalid choice."
            )

            continue

        print()
        print(
            f"[Controller] Selected: {mode}"
        )

        run_selected_mode(mode)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Telemetry child process
    # --------------------------------------------------------

    if len(sys.argv) >= 2:

        if sys.argv[1] == "--telemetry":

            telemetry_process_main()

            sys.exit(0)

    # --------------------------------------------------------
    # Normal controller
    # --------------------------------------------------------

    controller_main()