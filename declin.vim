" vim: ft=vim ts=2 sw=2 et
"
if exists("b:current_syntax")
  finish
endif
let b:current_syntax = "declin"


syntax match declinTrailingWhitespace / \+$/ containedin=ALL
highlight default link declinTrailingWhitespace Error

"syntax keyword declinCommand COLUMN ITEM LINE ROW contained
syntax match declinCommand /^[A-Z_]\+\ze\( \|$\)/ contained
syntax match declinSpecialCommand /^!\(DEFAULT\|EXPORT\)/ contained

syntax match declinCommandWrapper /^\S\+/ contains=declinCommand,declinSpecialCommand nextgroup=declinCommandArg


syntax match declinCommandArg /\s+\S\+/ contained

syntax match declinAssignment /^\s\+[a-zA-Z_]\+ *.\+/ contains=declinVarName,declinList,declinString,declinBool,declinInt,declinColor,declinBrokenColor

syntax match declinVarName /^\s\+\S\+/ contained contains=declinEquals
syntax match declinEquals / *\zs=/ contained
"syntax match declinAssignmentRightSide /=\zs.*/ contained contains=declinList

syntax match declinList /\[[^\]]*\]/ contains=declinListSymbols
syntax match declinListSymbols /[\[\],]/ contained

syntax match declinString /\("[^"]*"\|'[^']*'\)/

syntax match declinInt /\s\zs[0-9]\+\ze\(\s\|$\)/

"/x{3}|x{4}|x{6}|x{8}/


"syntax match declinBrokenColor /#[a-fA-F0-9]\+\ze\(\s\|$\)/
syntax match declinColor /#\(\([a-fA-F0-9]\{3}\)\{1,2}\|\([a-fA-F0-9]\{4}\)\{1,2}\)\ze\(\s\|$\)/

syntax keyword declinBool true false contained

highlight default link declinCommand Statement
highlight default link declinSpecialCommand Keyword
highlight default link declinVarName Identifier
highlight default link declinEquals Operator
highlight default link declinListSymbols Operator
highlight default link declinString String
highlight default link declinBool Boolean
highlight default link declinInt Number

highlight default link declinBrokenColor Error
highlight default link declinColor Number

syntax match declinComment /;.*/
highlight default link declinComment Comment
