ifeq ($(strip $(PVSNESLIB_HOME)),)
$(error run: source ~/sfc_lora/env.sh)
endif
export ROMNAME := candy
export ROMTITLE := CANDY MATCH3
AUDIOFILES := res/effectssfx.it res/song.it
export SOUNDBANK := res/soundbank
SMCONVFLAGS := -s -o $(SOUNDBANK) -V -b 5 -f
include ${PVSNESLIB_HOME}/devkitsnes/snes_rules
.PHONY: all
all: musics buildWithSummary
buildActual: $(OBJS) $(ROMNAME).sfc
musics: $(SOUNDBANK).obj
clean: cleanBuildRes cleanRom cleanGfx
