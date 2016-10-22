import time

from src.context import IRCContext, Features

Main = None # main channel

all_channels = {}

_states = ("not yet joined", "pending join", "joined", "pending leave", "left channel", "", "quit", "deleted", "cleared")

def _strip(name):
    return name.lstrip("".join(Features["STATUSMSG"]))

def get(name):
    """Return an existing channel, or raise a KeyError if it doesn't exist."""

    return all_channels[_strip(name)]

def add(name, cli):
    """Add and return a new channel, or an existing one if it exists."""

    name = _strip(name)

    if name in all_channels:
        if cli is not all_channels[name].client:
            raise RuntimeError("different IRC client for channel {0}".format(name))
        return all_channels[name]

    chan = all_channels[name] = Channel(name, cli)
    return chan

def exists(name):
    """Return True if a channel with the name exists, False otherwise."""

    return _strip(name) in all_channels

class Channel(IRCContext):

    is_channel = True

    def __init__(self, name, client):
        super().__init__(name, client)
        self.users = set()
        self.modes = {}
        self.timestamp = None
        self.state = 0

    def __str__(self):
        return "{self.__class__.__name__}: {self.name} ({_states[self.state]})".format(self=self)

    def __repr__(self):
        return "{self.__class__.__name__}({self.name})".format(self=self)

    def join(self, key=""):
        if self.state in (0, 4):
            self.state = 1
            self.client.send("JOIN {0} :{1}".format(self.name, key))

    def part(self, message=""):
        if self.state == 2:
            self.state = 3
            self.client.send("PART {0} :{1}".format(self.name, message))

    def kick(self, target, message=""):
        if self.state == 2:
            self.client.send("KICK {0} {1} :{2}".format(self.name, target, message))

    def mode(self, *changes):
        if not changes:
            self.client.send("MODE", self.name)
            return

        max_modes = Features["MODES"]
        params = []
        for change in changes:
            if isinstance(change, str):
                change = (change, None)
            params.append(change)
        params.sort(key=lambda x: x[0][0])

        while params:
            cur, params = params[:max_modes], params[max_modes:]
            modes, targets = zip(*cur)
            prefix = ""
            final = []
            for mode in modes:
                if mode[0] == prefix:
                    mode = mode[1:]
                elif mode.startswith(("+", "-")):
                    prefix = mode[0]

                final.append(mode)

            for target in targets:
                if target is not None:
                    final.append(" ")
                    final.append(target)

            self.client.send("MODE", self.name, "".join(final))

    def update_modes(self, rawnick, mode, targets):
        set_time = int(time.time()) # for list modes timestamp
        list_modes, all_set, only_set, no_set = Features["CHANMODES"]
        status_modes = Features["PREFIX"].values()

        i = 0
        for c in mode:
            if c in ("+", "-"):
                prefix = c
                continue

            if prefix == "+":
                if c in status_modes:
                    if c not in self.modes:
                        self.modes[c] = set()
                    val = user.get(targets[i], allow_bot=True)
                    self.modes[c].add(val)
                    val.channels[self].add(c)
                    i += 1

                elif c in list_modes:
                    if c not in self.modes:
                        self.modes[c] = {}
                    self.modes[c][targets[i]] = (rawnick, set_time)
                    i += 1

                else:
                    if c in no_set:
                        targ = None
                    else:
                        targ = targets[i]
                        i += 1
                    if c in only_set and targ.isdigit(): # +l/+j
                        targ = int(targ)
                    self.modes[c] = targ

            else:
                if c in status_modes:
                    if c in self.modes:
                        val = user.get(targets[i], allow_bot=True)
                        self.modes[c].discard(val)
                        val.channels[self].discard(c)
                        if not self.modes[c]:
                            del self.modes[c]
                    i += 1

                elif c in list_modes:
                    if c in self.modes:
                        self.modes[c].pop(targets[i], None)
                        if not self.modes[c]:
                            del self.modes[c]
                    i += 1

                else:
                    if c in all_set:
                        i += 1 # -k needs a target, but we don't care about it
                    del self.modes[c]

