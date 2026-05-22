#NOTE: (Ahmayk) independent files with no dependencies
from hq_config import *
from hq_strings import *
from hq_types import *

#NOTE: (Ahmayk) define functionality, dependent on each other
from hq_discord import *
from hq_react import *
from hq_rip import *
from hq_vet import *
from hq_sheets import *

#NOTE: (Ahmayk) define discord bot events and commands
from hq_events import *
from hq_commands import *
from hq_fun import *

from bot_secrets import TOKEN

bot.run(TOKEN)