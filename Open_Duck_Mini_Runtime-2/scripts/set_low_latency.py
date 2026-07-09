"""设置 ttyACM0 低延迟并测试舵机通信"""
import termios, os, fcntl, struct

def set_low_latency(fd):
    """通过 TIOCSSERIAL ioctl 设置 ASYNC_LOW_LATENCY"""
    # TIOCGSERIAL = 0x541E, TIOCSSERIAL = 0x541F
    TIOCGSERIAL = 0x541E
    TIOCSSERIAL = 0x541F
    ASYNC_LOW_LATENCY = 0x2000

    # serial_struct format: int type, int line, ui port, int irq, int flags, ...
    buf = bytearray(72)
    try:
        fcntl.ioctl(fd, TIOCGSERIAL, buf)
        flags = struct.unpack_from("<I", buf, 16)[0]
        flags |= ASYNC_LOW_LATENCY
        struct.pack_into("<I", buf, 16, flags)
        fcntl.ioctl(fd, TIOCSSERIAL, buf)
        return True
    except OSError as e:
        print(f"ioctl failed: {e}")
        return False

fd = os.open("/dev/ttyACM0", os.O_RDWR | os.O_NOCTTY)
print(f"fd={fd}")

# 方法1: TIOCSSERIAL
if set_low_latency(fd):
    print("TIOCSSERIAL low_latency set OK")

# 方法2: termios 最小化延迟
attrs = termios.tcgetattr(fd)
attrs[4] = attrs[4] & ~termios.ECHO
attrs[6][termios.VMIN] = 0
attrs[6][termios.VTIME] = 1
termios.tcsetattr(fd, termios.TCSAFLUSH, attrs)
print("termios VMIN=0 VTIME=1 set OK")

os.close(fd)
print("Done. Re-run the walk script now.")
