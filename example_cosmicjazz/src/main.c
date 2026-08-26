#include <snes.h>
#include "../res/soundbank.h"
extern char candygfx, candygfx_end, candypal;
extern char titlegfx, titlegfx_end, titlemap, titlepal;
extern char overgfx, overgfx_end, overmap, overpal;
extern char playgfx, playgfx_end, playmap, playpal;
extern char SOUNDBANK__;
#define ST_TITLE 0
#define ST_PLAY 1
#define ST_OVER 2
unsigned char grid[36];
unsigned char hit[36];             /* 1 = this cell was just cleared -> pop/flash during react */
unsigned char cx=2, cy=2, state=0, entered=0;
unsigned short timer=0;
unsigned char react=0, combo=0;   /* per-event mascot reaction: react=frames left, combo=cascade depth */
unsigned char sox=0, soy=0;        /* screen-shake offset applied to every OBJ + the BG */
unsigned char sfx=0;               /* set on match -> play SFX once from the main loop */
#define SFX_MATCH 0                /* effectssfx.it sample index (marimba) */
static void draw_candy(unsigned short slot, unsigned char col, unsigned char row, unsigned char id){
    /* gfx4snes reflows the 32x192 sheet into 4x2 blocks of 32x32 in the 16-tile-wide OBJ grid,
       so the base tile of piece id is (id>>2)*64 + (id&3)*4, not id*16. */
    unsigned char base = (id>>2)*64 + (id&3)*4;
    oamSet(slot<<2, col*32+32+sox, row*32+16+soy, 3,0,0, base, 0); oamSetEx(slot<<2, OBJ_LARGE, OBJ_SHOW);
}
static void draw_cursor(void){ oamSet(36<<2, cx*32+32+sox, cy*32+16+soy, 0,0,0, 0, 0); oamSetEx(36<<2, OBJ_LARGE, OBJ_SHOW); }
static const unsigned char BOB[4]  = {0, 1, 2, 1};              /* gentle idle bob */
static const unsigned char JUMP[8] = {0, 3, 6, 8, 8, 6, 3, 0};  /* big reaction jump */
static void draw_mascot(unsigned char slot, unsigned short x, unsigned char y, unsigned char id, unsigned char hf){
    unsigned char base = (id>>2)*64 + (id&3)*4;   /* rabbit=id6->72, groundhog=id7->76 (same sheet) */
    oamSet(slot<<2, x, y, 3,hf,0, base, 0); oamSetEx(slot<<2, OBJ_LARGE, OBJ_SHOW);
}
static void load_bg(char *g, unsigned short sz, char *m, char *p){
    setScreenOff(); dmaCopyVram(g,0x2000,sz); dmaCopyVram(m,0x1000,32*32*2); dmaCopyCGram(p,0,256);
    bgSetGfxPtr(0,0x2000); bgSetMapPtr(0,0x1000,SC_32x32); setScreenOn();
}
/* playable start: all 6 pieces, no initial 3-in-a-row, several swaps create a match */
static const unsigned char GRID0[36]={5,4,3,4,3,2,3,0,5,0,1,4,3,4,5,0,1,0,0,4,0,2,2,5,5,0,1,2,1,4,1,0,1,1,2,0};
static void init_grid(void){ unsigned char i; for(i=0;i<36;i++) grid[i]=GRID0[i]; }

void game_update(unsigned short pad, unsigned short down)
{
    int i, j, k, len, id, tmp;
    int x, y, x0, y0;
    int dx, dy;
    int changed;

    if (down & KEY_UP)
    {
        if (cy > 0) cy--;
    }
    if (down & KEY_DOWN)
    {
        if (cy < 5) cy++;
    }
    if (down & KEY_LEFT)
    {
        if (cx > 0) cx--;
    }
    if (down & KEY_RIGHT)
    {
        if (cx < 5) cx++;
    }

    if ((down & KEY_A) && (cx < 5))
    {
        int idx = cy * 6 + cx;
        tmp = grid[idx];
        grid[idx] = grid[idx + 1];
        grid[idx + 1] = tmp;

        combo = 0;
        for (i = 0; i < 36; i++) hit[i] = 0;   /* reset pop markers for this move */
        do
        {
            changed = 0;

            for (y = 0; y < 6; y++)
            {
                x = 0;
                while (x < 6)
                {
                    id = grid[y * 6 + x];
                    len = 1;
                    while ((x + len < 6) && (grid[y * 6 + x + len] == id))
                    {
                        len++;
                    }
                    if (len >= 3)
                    {
                        for (k = 0; k < len; k++)
                        {
                            hit[y * 6 + x + k] = 1;    /* mark cleared cell for the pop/flash */
                            grid[y * 6 + x + k] = (unsigned char)((id + 1) % 6);
                        }
                        changed = 1;
                    }
                    x += len;
                }
            }

            for (x = 0; x < 6; x++)
            {
                y = 0;
                while (y < 6)
                {
                    id = grid[y * 6 + x];
                    len = 1;
                    while ((y + len < 6) && (grid[(y + len) * 6 + x] == id))
                    {
                        len++;
                    }
                    if (len >= 3)
                    {
                        for (k = 0; k < len; k++)
                        {
                            hit[(y + k) * 6 + x] = 1;    /* mark cleared cell for the pop/flash */
                            grid[(y + k) * 6 + x] = (unsigned char)((id + 1) % 6);
                        }
                        changed = 1;
                    }
                    y += len;
                }
            }
            if (changed) combo++;
        } while (changed && combo < 6);   /* CAP cascades: recolour-to-(id+1) can re-match forever */
        if (combo) { react = 48; sfx = 1; }   /* trigger mascot reaction + match SFX; combo = cascade depth */
    }
}

int main(void){ unsigned char i;
  spcBoot(); setMode(BG_MODE1,0); bgSetDisable(1); bgSetDisable(2);
  oamInitGfxSet(&candygfx,(&candygfx_end-&candygfx),&candypal,256,0,0x0000,OBJ_SIZE16_L32);
  load_bg(&titlegfx,(&titlegfx_end-&titlegfx),&titlemap,&titlepal);
  init_grid(); spcSetBank(&SOUNDBANK__);
  spcStop(); spcLoad(MOD_SONG);                                   /* load music module */
  for(i=0;i<20;i++){ spcProcess(); WaitForVBlank(); }             /* let the queued load complete */
  spcLoadEffect(SFX_MATCH);                                       /* load effect sample (queued) */
  for(i=0;i<20;i++){ spcProcess(); WaitForVBlank(); }             /* let the effect load complete */
  spcPlay(0);
  while(1){ unsigned short pad=padsCurrent(0), down=padsDown(0);
    if(state==ST_TITLE){ if(!entered){load_bg(&titlegfx,(&titlegfx_end-&titlegfx),&titlemap,&titlepal);entered=1;}
      bgSetEnable(0); oamClear(0,128); if(down&KEY_START){state=ST_PLAY;entered=0;timer=0;} }
    else if(state==ST_PLAY){ if(!entered){load_bg(&playgfx,(&playgfx_end-&playgfx),&playmap,&playpal);entered=1;}
      bgSetEnable(0); game_update(pad,down);
      if(sfx){ spcEffect(2+combo, SFX_MATCH, 15*16+8); sfx=0; }  /* match SFX: pitch rises with combo depth */
      { unsigned char amp=(react>32)?(react-32):0;            /* match JUICE: shake offset (decays over ~16f) + flash */
        sox=(timer&1)?amp:0; soy=(timer&1)?0:amp;             /* whole board (OBJ) + BG jolt, diagonal each frame */
        bgSetScroll(0, sox, soy);
        setBrightness((react>40 && (react&1))?6:15); }        /* brightness flicker on impact */
      for(i=0;i<36;i++){                                    /* cleared candies POP: blink off on alternate frames */
        if(hit[i] && react>36 && (timer&2)){ oamSet(i<<2,0,240,0,0,0,0,0); oamSetEx(i<<2,OBJ_LARGE,OBJ_HIDE); }
        else draw_candy(i,i%6,i/6,grid[i]); }
      draw_cursor();
      if(react){ unsigned char jp=JUMP[(timer>>1)&7], sh=(timer&2)?1:0;  /* react: celebrate pose, big jump */
        draw_mascot(37, 0,   88-jp, 8, sh);                     /* rabbit cheer  (id8) */
        draw_mascot(38, 224, 88-jp, 9, sh^1);                   /* groundhog cheer (id9) */
        react--; }
      else { unsigned char ph=(timer>>3)&3, sw=(timer>>4)&1;   /* idle dance: bob + sway to the beat */
        draw_mascot(37, 0,   88+BOB[ph],       6, sw);
        draw_mascot(38, 224, 88+BOB[(ph+2)&3], 7, sw^1); }
      { unsigned short tc=(timer&16)?RGB5(31,31,31):RGB5(8,8,12); setPaletteColor(1,tc); } /* star twinkle: cycle reserved BG idx1 */
      timer++; if(timer>1800){state=ST_OVER;entered=0;} }
    else { if(!entered){oamClear(0,128);load_bg(&overgfx,(&overgfx_end-&overgfx),&overmap,&overpal);entered=1;}
      bgSetEnable(0); if(down&KEY_START){state=ST_TITLE;entered=0;} }
    spcProcess(); WaitForVBlank(); }
  return 0; }
