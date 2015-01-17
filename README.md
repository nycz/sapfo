Sapfo
=====

A program for writers to organize what they write using tags.
To let Sapfo find your files, create a .metadata file for each file
and then set the root path in Sapfo's config to the directory your
files are in.

The metadata files are named .[originalfilename].metadata (including
dots but excluding brackets)

Example:

    root/
        super-fun-story.txt
        .super-fun-story.txt.metadata
        Hamlet and the Unicorn.txt
        .Hamlet and the Unicorn.txt.metadata

The first time you start Sapfo, it will copy its default config to `~/.config/sapfo/settings.json` and then immediately crash. To make Sapfo work correctly, you have to set the config's `path` option to a directory where you want your files to be stored, preferably one only meant for this purpose. With that set, Sapfo should work.


Metadata files
--------------
*These should really be automagically generated and then edited inside sapfo.*

The metadata files are written in json. For now, the three values that has to be present is `title` (string), `description` (string) and `tags` (list).
All of them can be empty but at least with `title` it is not recommended.

Example:

```json
{
    "title": "Hamlet and the Unicorn",
    "description": "The riveting tale about Hamlet and his amazing unicorn."
    "tags": [
        "adventure",
        "romance",
        "drama"
    ]
}
```

Command-line options
--------------------
View all available options by running `sapfo -h` or `sapfo --help`.


The config
----------
####path####
The path to the root directory where Sapfo store all its files. **Sapfo will not work without a valid path.**

####title####
The text to show in the titlebar. If not set, "Sapfo" will be shown in the titlebar.

####hotkeys####
The hotkeys are for the viewer (when you have opened an entry inside sapfo) and should be rather self-explanatory. All hotkey options can have multiple hotkeys set. **Note that leaving "home" empty means you have no way to get back to the index when viewing an entry.**

####editor####
A command that will be invoked with the chosen entry's file path when using the `x` command. For example, if the editor is `vim`, the result would be `vim /path/to/entrys/file.txt`.

####tag colors####
A dict where the keys are tags and the values are colors. The tags' boxes in the index view will use this color. Note that the tags' text color is set in the style config and isn't touched by this setting, so try to avoid unreadable color pairs (eg. black on dark gray).

**Example:**

```json
"tag colors": {
    "tragedy": "black",
    "happy times": "#9c8",
    "non-fiction": "#ccddaa"
}
```

####formatting converters####
This option is here to convert one kind of formatting to html, so files are pretty and formatted in the viewer. The option is a list of lists, where the sublists are either two or three items long. The first item is what is to be searched for, the second is what it will be replaced with, and the third (and optional) item is where the search will take place. All items are python regexes. Remember to escape backslashes!

**Example 1** (Replacing all `* * *` with horizontal lines (`<hr>`))

`["\\* \\* \\*", "<hr />"],`

**Example 2** (Wrapping lines with `<p>`)

`["(?m)^(.+?)$", "<p>\\1</p>"],`

**Example 3** (Replace asterisks around words with `<strong>` but only inside `<em>` tags. Don't ask me why.)

`["\\*(.+?)\\*", "<strong>\\1</strong>", "<em>.+?</em>"]`

####chapter strings####
This option is here to let sapfo find (and format) chapters in your stories. It is a list of lists (pairs). The first item is a regex to match/find all lines with chapter titles and the second item is a simple string with how the result will be formatted. All groups (specified with `(?P<name>[...])`) in the regex will be attempted to be matched with the format strings groups. Eg. `(?P<name>.+?)` would be matched with `{name}`.

**Example 1** (the result will be "Chapter 1")

```json
[
  "CHAPTER (?P<num>\\d+)\\s*$",
  "Chapter {num}"
]
```

**Example 2** (the result will be "Chapter 1 - Chapter Title")

```json
[
  "CHAPTER (?P<num>\\d+) ?[:-] (?P<name>.+)",
  "Chapter {num} - {name}"
]
```


Usage
-----
Everything is done in the *Terminal*. Love it, be one with it.
Commands are executed with (surprise) Enter, and a history of previous commands is accessible with Up/Down arrow keys.

All commands are one character, but some may have one or more arguments.

###Commands###

Space should be omitted unless explicitly specified.

Tab-/autocompletion works for tag commands: `ft` and `et`.

####Entry handling####
* `<number>` – open the entry with the corresponding number
* `x<number>` – open the entry with the chosen program/command
    * Make sure you set the `editor` value in config to the program to open the entry with.
* `x<text> – open the entry with `<text>` in the title with the chosen program/command
    * If multiple entries match, nothing will be opened.
* `q` – quit

#####New entry#####
`n ([<tag>, <tag>, ...]) <path>`

The `n` command creates a new file and an accompanying metadatafile automagically that includes the tags specified. The path is relative to the root path specified in the config. Directories that do not exist will not be created. If a file (but not a matching metadatafile) exists, Sapfo will notify you of this but still go ahead and create the metadatafile. The file itself will not be changed.

**Note that the parentheses around the tags are mandatory, even if you don't want to add any tags.** Duplicate tags are removed. Both the tags and the path are autocompleted.

The title will be autogenerated from the filename, converting dashes to space and capitalizing the first letter in each word.

**Examples:**

* `n (tag1, tag2) super-fun-story.txt` – Results in the entry "Super Fun Story" with two tags.
* `n () bloop.txt` – Results in the entry "Bloop" with no tags.
* `n (shakespeare, hamlet) angst/hamlet-and-the-unicorn.md` – Results in the entry "Hamlet And The Unicorn" with two tags. Will show an error if the directory "angst" doesn't exist.

####Edit####
* `e(n|d|t)<number>[ (<text>|<tag>[, ...])]` – change name (`n`), description (`d`) or tags (`t`) for entry at `<number>` to `<text>` or `<tag>`s.
    * If `<text>` and `<tag>` are both omitted, the current value is inserted in the terminal for your convenience.
* `et*[<oldtag>],[<newtag>]` – replace all **visible** instances of `<oldtag>` with `<newtag>`. Tags not visible due to filters are unchanged. Omitting `<oldtag>` adds `<newtag>` to all visible entries. Omitting `<newtag>` removes all instances of `<oldtag>`.
* `eu` – undo last edit (there is no limit to how many undos can exist)

**Tags may not include the following characters:** `()|,` **and may not begin with `-` or `@`.**

####Filter####
* `f` – reset filter
* `f-` – undo the last filter
* `f(n|d)<text>` – show entries where `<text>` is found in either name (`n`) or description (`d`) (Case-insensitive) Leave `<text>` empty to show entries without name or description.
* `ft` – see *Filtering Tags*
* `fl(<=|>=|<|>)<number>[...]` – show entries whose lengths match the expression(s). The letter 'k' in `<number>` is automagically converted into *1000 (`2k` = `2000`). The expressions can be stacked without delimiters, eg. `fl<10000>=1500`

#####Filtering Tags#####
In essence, it's a whole bunch of ORs (`|`) and ANDs (`,`) with parentheses to indicate precedence. Whitespace between tags is irrelevant. Prefix single tags with `-` to invert them (only show entries that don't include the prefixed tag). Leave the filter completely blank to show all entries without tags.

**Examples:**

* `ft tag1, tag2, (tag3 | -tag4)` – Shows entries that has tag1 and tag2 and (tag3 or not tag4).
* `ft tag1|(tag2,(tag3|tag4),tag5)|tag6` – Shows entries that has tag1 or (tag 2 and (tag3 or ta)).
* `ft tag1 | tag2, tag3` – This will give an error since OR and AND can't coexist without parentheses.
* `ft tag1 | (tag2, (tag3 | (tag4, (tag5 | (tag6, tag7)))))` – Parentheses can be nestled without limits. Yay.
* `ft foo* | *bar` – Asterisks can be used as wildcards. This filter will match any entry with a tag starting with "foo" or a tag ending with "bar".
* `ft` – Shows all entries without tags.

####Sort####
* `s` – show the current sort order
* `s(n|l)[-]` – sort after name (`n`) or length (`l`). `-` sorts descendingly

####List####
* `l(f|t[a])` – list active filters (`f`) or all tags (`t`). Add `a` when listing tags to show them in alphabetical order instead of usage numbers.
    * The popup screen shown from `lt[a]` is closed by pressing enter, with or without a command entered in the terminal (a command will be executed if present).


The style config
----------------
While the actual stylesheets aren't configurable directly, Sapfo provides a simple json file to config certain values. The file is called `style.json` and is copied to Sapfo's config directory if it isn't present.

Most settings should be obvious but if not, check the files `index_page.css`, `viewer_page.css` and `template.css` in the sapfo directory (not the config directory) to see what the values actually changes. The values should always be CSS-compatible. Check `defaultstyle.json` or read up on CSS to learn more.


Note to self
------------
Use load() instead of setUrl(). Segfaults start popping up all over the place when setUrl is around...
