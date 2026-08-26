.include "hdr.asm"
.section ".rd_candy" superfree
candygfx: .incbin "res/candy.pic"
candygfx_end:
candypal: .incbin "res/candy.pal"
.ends
.section ".rd_title" superfree
titlegfx: .incbin "res/title.pic"
titlegfx_end:
titlemap: .incbin "res/title.map"
titlepal: .incbin "res/title.pal"
.ends
.section ".rd_over" superfree
overgfx: .incbin "res/over.pic"
overgfx_end:
overmap: .incbin "res/over.map"
overpal: .incbin "res/over.pal"
.ends
.section ".rd_play" superfree
playgfx: .incbin "res/play.pic"
playgfx_end:
playmap: .incbin "res/play.map"
playpal: .incbin "res/play.pal"
.ends
