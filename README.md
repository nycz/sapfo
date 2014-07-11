Sapfo
=====

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

Tab-/autocompletion works for tag commands: `ft` and `et`.

####Entry handling####
* `<number>` – open the entry with the corresponding number
* `x<number>` – open the entry with the chosen program/command
    * Make sure you set the `editor` value in config to the program to open the entry with.
* `q` – quit

####Edit####
* `e(n|d|t)<number>[ (<text>|<tag>[, ...])]` – change name (`n`), description (`d`) or tags (`t`) for entry at `<number>` to `<text>` or `<tag>`s.
    * If `<text>` and `<tag>` are both omitted, the current value is inserted in the terminal for your convenience.
* `et*[<oldtag>],<newtag>` – replace all **visible** instances of `<oldtag>` with `<newtag>`. Tags not visible due to filters are unchanged. Omitting `<oldtag>` adds `<newtag>` to all visible entries.
* `eu` – undo last edit (there is no limit to how many undos can exist)

####Filter####
* `f` – reset filter
* `f(n|d)<text>` – show entries where `<text>` is found in either name (`n`) or description (`d`) (Case-insensitive)
* `ft – see *Filtering Tags*
* `fl(<=|>=|<|>)<number>[...]` – show entries whose lengths match the expression(s). The letter 'k' in `<number>` is automagically converted into *1000 (`2k` = `2000`). The expressions can be stacked without delimiters, eg. `fl<10000>=1500`

#####Filtering Tags#####
In essence, it's a whole bunch of ORs (`|`) and ANDs (`,`) with parentheses to indicate precedence. Whitespace between tags is irrelevant. Prefix single tags with `-` to invert them (only show entries that don't include the prefixed tag).
* `ft tag1, tag2, (tag3 | -tag4)` – Shows entries that has tag1 and tag2 and (tag3 or not tag4).
* `ft tag1|(tag2,(tag3|tag4),tag5)|tag6` – Shows entries that has tag1 or (tag 2 and (tag3 or ta))
Note that an OR and an AND can not exist together without parentheses. This will result in an error:
* `ft tag1 | tag2, tag3`
Parentheses can be nestled without limits. Yay.
* `ft tag1 | (tag2, (tag3 | (tag4, (tag5 | (tag6, tag7)))))
Asterisks `*` can be used as wildcards. This filter will match any entry with a tag starting with "foo" or a tag ending with "bar"
* `ft foo* | *bar`


####Sort####
* `s(n|l)[-]` – sort after name (`n`) or length (`l`). `-` sorts descendingly

####List####
* `l(f|t[a])` – list active filters (`f`) or all tags (`t`). Add `a` when listing tags to show them in alphabetical order instead of usage numbers.
    * The popup screen shown from `lt[a]` is closed by pressing enter, with or without a command entered in the terminal (a command will be executed if present).

By the way
----------
The config is good stuff, and sapfo will explode in your face the first time you start it, on purpose!
Sapfo helpfully copies the default config to the config path and then explodes.
You have to edit the config before it will work.

Path to the config's directory is `~/.config/sapfo/`


Note to self
------------
Use load() instead of setUrl(). Segfaults start popping up all over the place when setUrl is around...
