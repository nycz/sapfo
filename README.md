What is this
------------

A program to view and sort downloaded stories (eg. fanfiction),
organized as a rootdirectory with each story (one or more files) in
a subdirectory under, with an accompanying metadata-file.

Example:

    root/
      Super Fun Story/
        metadata.json
        super_fun_story.html
      Hamlet and the Unicorn/
        metadata.json
        hamletpg01.html
        hamletpg02.html


metadata.json
-------------
If you use sapfo-dl (when it's done (better)) one should be generated automagically.
Otherwise you can make one yourself, or maybe sapfo helps you out there. I don't think so though.

For now, the three values that has to be present is `title` (string), `description` (string) and `tags` (list).
All of them can be empty but at least with `title` it is not recommended.


Usage
-----
Everything is done in the *Terminal*. Love it, be one with it.
Commands are entered with (surprise) Enter, and a history of previous commands is accessible with Up/Down arrow keys.

All commands are one character, but some may have one or more arguments.

###Commands###

Space should be omitted unless explicitly specified.
Characters in square brackets are mutually exclusive and can not be used at the same time.
ALLCAPS words are variables the users should fill in themselves, eg. TEXT or NUMBER.

Tab-/autocompletion works for tag commands: `ft` and `et`.

* `NUMBER` - open (by number)
    * a lone `NUMBER` opens the story with the corresponding number (if it exists)
* `f[ndt]TEXT` - filter
    * `n` filters by name(title)
    * `d` filters by description
    * `t` filters by tags
        * If TEXT starts with `-`, the filtering will be inverted
        * If TEXT contains `*`, that will be treated as a wildcard (at least one character)
    * Omitting arguments and `TEXT` will reset the filter, showing all entries.
* `flEXPRESSIONS` - filter (by wordcount)
    * `EXPRESSIONS` are one of `<= >= < >` and a number, multiple are allowed (eg `fl<10000>=1500`)
    * the letter 'k' in a number in the `EXPRESSIONS` is automagically converted into *1000 (2k = 2000)
* `s[nl][-]` - sort
    * `n` sorts after name(title)
    * `l` sorts after wordcount
    * `-` makes the sort descending (optional)
* `e[ndt]NUMBER VALUE` - edit
    * *note the space between `NUMBER` and `VALUE`!*
    * `n` edits the name(title)
    * `d` edits the description
    * `t` edits the tags
    * `NUMBER` is the id of the story (visible to the left of the title)
    * `VALUE` is a string for `n` and `d`, and a comma-separated list for `t` (eg `et12 tag1,tag2`)
    * if `VALUE` is omitted, the current value is inserted in the terminal for your convenience.
* `et*[OLDTAG],NEWTAG` - replace a tag
    * Replaces all visible instances of `OLDTAG` with `NEWTAG`.
    * *Note that this only changes the instances visible after filtering! To replace all instances, reset the filters first.*
    * To simply add a tag to all visible entries, omit `OLDTAG` *but remember the comma!*
* `eu` - undo edit
    * Undoes last edit. The undo stack does not have a limit.
* `xNUMBER` - open the entry with the chosen program/command
    * Make sure you set the `editor` value in config to the program to open the entry with.
* `l[ft][a]` - list active filters or all tags
    * `f` prints all active filters in the terminal
    * `t` opens a popup~ish screen with a list of all tags and the times they are used, sorted descendingly after number of uses.
        * Add an `a` after `lt` to instead sort alphabetically.
        * The screen is closed by pressing enter, with or without a command entered in the terminal (a command will be executed if present).

By the way
----------
The config is good stuff, and sapfo will explode in your face the first time you start it, on purpose!
Sapfo helpfully copies the default config to the config path and then explodes.
You have to edit the config before it will work.

Path to the config's directory is `~/.config/sapfo/`


Note to self
------------
Use load() instead of setUrl(). Segfaults start popping up all over the place when setUrl is around...
