import fnmatch
from collections import defaultdict

import botconfig
from oyoyo.parse import parse_nick
from src import settings as var
from src import logger

adminlog = logger(None)

COMMANDS = defaultdict(list)
HOOKS = defaultdict(list)

class cmd:
    def __init__(self, *cmds, raw_nick=False, admin_only=False, owner_only=False,
                 chan=True, pm=False, join=False, none=False, game=False, playing=False, roles=()):

        self.cmds = cmds
        self.raw_nick = raw_nick
        self.admin_only = admin_only
        self.owner_only = owner_only
        self.chan = chan
        self.pm = pm
        self.join = join
        self.none = none
        self.game = game
        self.playing = playing
        self.roles = roles
        self.func = None
        self.aftergame = False
        self.name = cmds[0]

        alias = False
        self.aliases = []
        for name in cmds:
            for func in COMMANDS[name]:
                if (func.owner_only != owner_only or
                    func.admin_only != admin_only):
                    raise ValueError("unmatching protection levels for " + func.name)

            COMMANDS[name].append(self)
            if alias:
                self.aliases.append(self)
            alias = True

    def __call__(self, func):
        self.func = func
        self.__doc__ = self.func.__doc__
        return self

    def caller(self, *args):
        largs = list(args)

        cli, rawnick, chan, rest = largs
        nick, mode, user, cloak = parse_nick(rawnick)

        if cloak is None:
            cloak = ""

        if not self.raw_nick:
            largs[1] = nick

        if nick == "<console>":
            return self.func(*largs) # special case; no questions

        if not self.pm and chan == nick:
            return # PM command, not allowed

        if not self.chan and chan != nick:
            return # channel command, not allowed

        if chan.startswith("#") and chan != botconfig.CHANNEL and not (admin_only or owner_only):
            if "" in self.cmds:
                return # don't have empty commands triggering in other channels
            for command in self.cmds:
                if command in botconfig.ALLOWED_ALT_CHANNELS_COMMANDS:
                    break
            else:
                return

        if nick in var.USERS and var.USERS[nick]["account"] != "*":
            acc = var.USERS[nick]["account"]
        else:
            acc = None

        if "" in self.cmds:
            return self.func(*largs)

        if self.game and var.PHASE not in ("day", "night") + (("join",) if self.join else ()):
            if chan == nick:
                pm(cli, nick, "No game is currently running.")
            else:
                cli.notice(nick, "No game is currently running.")
            return

        if ((self.join and self.none and var.PHASE not in ("join", "none")) or
                     (self.none and not self.join and var.PHASE != "none")):
            if chan == nick:
                pm(cli, nick, "Sorry, but the game is already running. Try again next time.")
            else:
                cli.notice(nick, "Sorry, but the game is already running. Try again next time.")
            return

        if self.join and not self.none:
            if var.PHASE == "none":
                if chan == nick:
                    pm(cli, nick, "No game is currently running.")
                else:
                    cli.notice(nick, "No game is currently running.")
                return

            if var.PHASE != "join" and not self.game:
                if chan == nick:
                    pm(cli, nick, "Werewolf is already in play.")
                else:
                    cli.notice(nick, "Werewolf is already in play.")
                return

        if self.playing and (nick not in var.list_players() or nick in var.DISCONNECTED):
            if chan == nick:
                pm(cli, nick, "You're not currently playing.")
            else:
                cli.notice(nick, "You're not currently playing.")
            return

        if self.roles:
            for role in self.roles:
                if nick in var.ROLES[role]:
                    break
            else:
                return

            return self.func(*largs) # don't check restrictions for role commands

        if acc:
            for pattern in var.DENY_ACCOUNTS:
                if fnmatch.fnmatch(acc.lower(), pattern.lower()):
                    for command in self.cmds:
                        if command in var.DENY_ACCOUNTS[pattern]:
                            if chan == nick:
                                pm(cli, nick, "You do not have permission to use that command.")
                            else:
                                cli.notice(nick, "You do not have permission to use that command.")
                            return

            for pattern in var.ALLOW_ACCOUNTS:
                if fnmatch.fnmatch(acc.lower(), pattern.lower()):
                    for command in self.cmds:
                        if command in var.ALLOW_ACCOUNTS[pattern]:
                            if self.admin_only or self.owner_only:
                                adminlog(chan, rawnick, self.name, rest)
                            return self.func(*largs)

        if not var.ACCOUNTS_ONLY and cloak:
            for pattern in var.DENY:
                if fnmatch.fnmatch(cloak.lower(), pattern.lower()):
                    for command in self.cmds:
                        if command in var.DENY[pattern]:
                            if chan == nick:
                                pm(cli, nick, "You do not have permission to use that command.")
                            else:
                                cli.notice(nick, "You do not have permission to use that command.")
                            return

            for pattern in var.ALLOW:
                if fnmatch.fnmatch(cloak.lower(), pattern.lower()):
                    for command in self.cmds:
                        if command in var.ALLOW[pattern]:
                            if self.admin_only or self.owner_only:
                                adminlog(chan, rawnick, self.name, rest)
                            return self.func(*largs)

        if self.owner_only:
            if var.is_owner(nick, cloak):
                adminlog(chan, rawnick, self.name, rest)
                return self.func(*largs)

            if chan == nick:
                pm(cli, nick, "You are not the owner.")
            else:
                cli.notice(nick, "You are not the owner.")
            return

        if self.admin_only:
            if var.is_admin(nick, cloak):
                adminlog(chan, rawnick, self.name, rest)
                return self.func(*largs)

            if chan == nick:
                pm(cli, nick, "You are not an admin.")
            else:
                cli.notice(nick, "You are not an admin.")
            return

        return self.func(*largs)

class hook:
    def __init__(self, name, hookid=-1):
        self.name = name
        self.hookid = hookid
        self.func = None

        HOOKS[name].append(self)

    def __call__(self, func):
        self.func = func
        self.__doc__ = self.func.__doc__
        return self

    def caller(self, *args):
        return self.func(*args)

    @staticmethod
    def unhook(hookid):
        for each in list(HOOKS):
            for inner in list(HOOKS[each]):
                if inner.hookid == hookid:
                    HOOKS[each].remove(inner)
            if not HOOKS[each]:
                del HOOKS[each]
