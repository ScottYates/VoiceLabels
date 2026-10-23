"""Settings for the voice label printer. Edit these to match your hardware."""

# --- Label geometry -------------------------------------------------------
DPI = 203                     # Zebra GK420d / GC420d print head resolution
# How the labels sit in the printer. Measure across the printer (side to side
# under the print head) and along the feed (the way the labels come out).
LABEL_WIDTH_IN = 3.0          # across the print head
LABEL_LENGTH_IN = 2.0         # along the feed

# "landscape" = text reads along the 3" side (label is 3" wide x 2" tall)
# "portrait"  = text reads along the 2" side (label is 2" wide x 3" tall)
ORIENTATION = "landscape"

# When the label's layout doesn't match how the roll is loaded (e.g. a
# portrait label on a roll that is wider than it is long), the image is turned
# a quarter turn before printing. If that text comes out upside down, change
# 90 to 270.
LANDSCAPE_ROTATE_DEG = 90

# How the label text lines up: "left", "center" or "right" (also on the
# Setup screen; the choice there is remembered).
TEXT_ALIGN = "left"

MARGIN_DOTS = 14              # blank border around the label (~0.07")

# --- Fonts ----------------------------------------------------------------
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
TEXT_MAX_PX = 140             # biggest the main text is allowed to get
TEXT_MIN_PX = 16              # smallest before the text is cut off
DATE_PX = 30

# --- Icons ------------------------------------------------------------------
# Icon sets searched online (Iconify). Solid, single-colour sets print best.
# Browse them at https://icon-sets.iconify.design
ICON_SETS = [
    "mdi", "material-symbols", "ph", "iconoven", "icon-park-solid", "bi", "lucide",
    "hugeicons", "carbon", "tabler", "mingcute", "fa6-solid", "game-icons", "maki",
    "energy-icons", "iconmind", "streamline-ultimate", "teenyicons", "clarity",
    "simple-icons",    # brand logos: Raspberry Pi, Arduino, Prusa, ...
]
# Extra words for the icon search: what you say -> what to search for, e.g.
#   ICON_SYNONYMS = {"zip ties": ["cable tie", "tie"]}
ICON_SYNONYMS = {}
ICON_TIMEOUT_SECONDS = 8
ICON_POSITION = "left"        # where a new icon goes: "left", "right", "top" or "bottom"
ICON_SIZE = "medium"          # "small", "medium" or "large"

# --- Date -----------------------------------------------------------------
DATE_FORMAT = "%b %d, %Y"     # e.g. "Oct 16, 2026". Try "%m/%d/%Y" or "%Y-%m-%d"
DATE_DEFAULT_ON = True

# --- QR code --------------------------------------------------------------
QR_DEFAULT_ON = False
QR_SIZE_FRACTION = 0.62       # QR side as a fraction of the label's short side

# --- Printer --------------------------------------------------------------
# Either write straight to the USB device (simplest), or name a CUPS raw queue.
PRINTER_DEVICE = "/dev/usb/lp0"
CUPS_QUEUE = None             # e.g. "zebra" to print with `lp -d zebra -o raw`
PRINT_DARKNESS = 15           # 0-30, Zebra ~SD setting; raise if print is faint
PRINT_SPEED_IPS = 3           # slower = crisper

# --- Physical buttons and their lights (BCM pin numbers) ------------------
TALK_BUTTON_PIN = 17          # GPIO17 (pin 11) to GND (pin 9)
TALK_LED_PIN = 27             # GPIO27 (pin 13), LED - to GND (pin 14); None if unused
PRINT_BUTTON_PIN = 22         # GPIO22 (pin 15) to GND (pin 20)
PRINT_LED_PIN = 23            # GPIO23 (pin 16), LED - to GND (pin 25); None if unused
PRINT_HOLD_SECONDS = 3.0      # default hold time for PRINT (screen or button)
PRINT_HOLD_CHOICES = [0, 1, 2, 3, 5]   # choices on the Setup screen; 0 = no hold
MIN_TALK_SECONDS = 0.35       # shorter presses of TALK are ignored
# Tap TALK, then press and hold it again within this many seconds: clear the
# text and start over (screen button or physical button).
DOUBLE_TAP_SECONDS = 0.6

# --- Speech ---------------------------------------------------------------
LANGUAGE = "en"
# The microphone is the input device whose name contains this text, on
# whichever USB port it's plugged into. Run `./run.sh stt.py --list` to see names.
MIC_NAME = "USB"
RECORD_MODE = "replace"       # "replace" the text, or "append" to it
TAIL_SECONDS = 0.35           # keep listening this long after release

# Spelling: when you spell a word out ("J A N E", or the recognizer writes
# J-A-N-E), the letters are joined back into one word: "" gives Jane.
# "-" keeps them apart: J-A-N-E. Set to None to leave them as they were heard.
SPELL_JOINER = ""
# How a joined word is capitalized: "name" gives Jane (and RJ45 when it has
# digits), "upper" gives JANE, "lower" gives jane.
SPELL_CASE = "name"

# Spoken commands: "space", "start over", "upper case", "lower case",
# "title case", "undo", "change ... to ..." and "remove ..." (the Help
# screen lists them). False treats them as words.
VOICE_COMMANDS = True

# Words the speech model should favor. Add part numbers, names and jargon you
# say often, spelled and capitalized exactly as you want them on the label.
# No commas inside a term. Restart the app after editing.
KEYTERMS = [
    "Bin", "M3", "M4", "M5", "M6", "M8",
]

# --- Screen ---------------------------------------------------------------
FULLSCREEN = True
# Turn the display off after this many seconds with no touch, key or button
# press (0 = never). The first touch on a dark screen only wakes it.
SCREEN_BLANK_SECONDS = 300
# Brightness choices on the Setup screen, in percent. The choice is
# remembered in settings.json and put back after the screen blanks.
BRIGHTNESS_LEVELS = [25, 50, 75, 100]
# Press and hold on the text box or the label preview this long to turn the
# screen off right away (0 = off).
LONG_PRESS_BLANK_SECONDS = 1.5
