"""
sh1106.py - Driver SH1106 para pantalla OLED I2C 1.3" (128x64)

Basado en el driver de MicroPython community.
Conexión I2C:
    SDA → GPIO16
    SCL → GPIO17
    VCC → 3.3V
    GND → GND
"""

from micropython import const
import framebuf


# Comandos SH1106
SET_CONTRAST = const(0x81)
SET_NORM_INV = const(0xA6)
SET_DISP = const(0xAE)
SET_MEM_ADDR = const(0x20)
SET_COL_ADDR = const(0x21)
SET_PAGE_ADDR = const(0x22)
SET_DISP_START_LINE = const(0x40)
SET_SEG_REMAP = const(0xA0)
SET_MUX_RATIO = const(0xA8)
SET_COM_OUT_DIR = const(0xC0)
SET_DISP_OFFSET = const(0xD3)
SET_COM_PIN_CFG = const(0xDA)
SET_DISP_CLK_DIV = const(0xD5)
SET_PRECHARGE = const(0xD9)
SET_VCOM_DESEL = const(0xDB)
SET_CHARGE_PUMP = const(0x8D)


class SH1106_I2C:

    def __init__(self, width, height, i2c, addr=0x3C):
        self.width = width
        self.height = height
        self.i2c = i2c
        self.addr = addr
        self.pages = height // 8
        self.buffer = bytearray(self.pages * self.width)
        self.framebuf = framebuf.FrameBuffer(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self._init_display()

    def _init_display(self):
        cmds = [
            SET_DISP | 0x00,          # display off
            SET_DISP_CLK_DIV, 0x80,
            SET_MUX_RATIO, 0x3F,      # 64 lines
            SET_DISP_OFFSET, 0x00,
            SET_DISP_START_LINE | 0x00,
            SET_CHARGE_PUMP, 0x14,     # charge pump on
            SET_MEM_ADDR, 0x00,
            SET_SEG_REMAP | 0x01,      # column remap
            SET_COM_OUT_DIR | 0x08,    # row remap
            SET_COM_PIN_CFG, 0x12,
            SET_CONTRAST, 0xCF,
            SET_PRECHARGE, 0xF1,
            SET_VCOM_DESEL, 0x40,
            SET_NORM_INV | 0x00,       # normal display
            SET_DISP | 0x01,           # display on
        ]
        for cmd in cmds:
            self._cmd(cmd)

    def _cmd(self, cmd):
        self.i2c.writeto(self.addr, bytes([0x80, cmd]))

    def show(self):
        """Envía el buffer completo a la pantalla."""
        for page in range(self.pages):
            self._cmd(0xB0 + page)      # set page address
            self._cmd(0x02)             # lower column start (offset 2 for SH1106)
            self._cmd(0x10)             # higher column start
            start = page * self.width
            data = bytearray([0x40]) + self.buffer[start:start + self.width]
            self.i2c.writeto(self.addr, data)

    def fill(self, color):
        self.framebuf.fill(color)

    def pixel(self, x, y, color=1):
        self.framebuf.pixel(x, y, color)

    def text(self, string, x, y, color=1):
        self.framebuf.text(string, x, y, color)

    def hline(self, x, y, w, color=1):
        self.framebuf.hline(x, y, w, color)

    def vline(self, x, y, h, color=1):
        self.framebuf.vline(x, y, h, color)

    def rect(self, x, y, w, h, color=1):
        self.framebuf.rect(x, y, w, h, color)

    def fill_rect(self, x, y, w, h, color=1):
        self.framebuf.fill_rect(x, y, w, h, color)

    def contrast(self, value):
        self._cmd(SET_CONTRAST)
        self._cmd(value)

    def invert(self, invert):
        self._cmd(SET_NORM_INV | (invert & 1))

    def poweroff(self):
        self._cmd(SET_DISP | 0x00)

    def poweron(self):
        self._cmd(SET_DISP | 0x01)
