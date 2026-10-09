# LayerHound status light (ring): a standing emblem for the desk, like the LayerHound logo.
#
#   python hardware/lightbar/housing/build_ring_housing.py      (from the project folder; see README.md here)
#
# Writes print-ready STL files to hardware/lightbar/housing/stl/ and an assembly.json the 3D viewer
# (viewer.html) uses to put them together. Every size is a setting at the top of this file.
#
# The parts:
#   head        a round cup, printed face-down: the front bezel and a window for the light
#   diffuser    translucent disc in the window, printed face-down, with the hound inlaid in the middle
#               (diffuser-emblem-*.stl: multicolor inlays, like the case lid)
#   paddle      the head's back plate and the stem below it, printed flat: three ribs hold the LED
#               ring against the diffuser, and the stem plugs into the base at the head's tilt
#   base        the plinth with LAYERHOUND on the front, printed top-down; the ESP32 and the small
#               level-shifter board go inside, the USB port at the back
#   base-bottom the floor, with pockets for 3M Bumpon SJ5302 feet
#
# Coordinates: the head parts are built facing up (+z is toward you, +y is up on the face); the
# base is built as it stands (z up from the desk, front at y=0, +y toward the back).
import json, math, sys
from pathlib import Path
from manifold3d import CrossSection, Manifold, set_circular_segments
from shapely.affinity import translate
from shapely.geometry import Point
from shapely.ops import unary_union

HERE=Path(__file__).resolve().parent; ROOT=HERE.parent.parent.parent
sys.path.insert(0,str(ROOT/'hardware/case'))
import emblem as emblem_mod
from build_case import box, cyl, rbox, save, section, text_shape, union

set_circular_segments(128)

# ---- Settings (mm) ------------------------------------------------------------------------
# Adafruit NeoPixel Ring, 12 LEDs (#1643): outside and inside diameter, and thickness with the LEDs
RING_OD=37.0; RING_ID=23.3; RING_T=6.7
# ESP32 38-pin "narrow" board as it sits on its header pins, and the small board with the 74AHCT125,
# capacitor and resistor (cut from a Perma-Proto or perfboard)
ESP_L=55.0; ESP_W=28.0; ESP_PINS=8.5; ESP_PCB=1.6
SHIFTER_BOARD=(28.0,40.0); SHIFTER_H=16.0   # width, length; tallest part (capacitor) lying down
FIT=0.25                  # gap between parts that slide together
WALL=2.4                  # walls of the head and base

# Head
HEAD_OD=64.0              # outside diameter of the round head
FRONT=2.0                 # front bezel thickness
WINDOW=41.0               # the light's window in the bezel (over the ring)
FLANGE=1.2; FLANGE_EXTRA=2.5   # diffuser flange behind the bezel, so it can't push out the front
PADDLE_T=3.0              # back plate thickness
WIRE_GAP=5.0              # room behind the ring for its three wires
EMBLEM_W=19.0             # the hound in the middle of the ring
INLAY=0.6                 # inlay depth (3 layers at 0.2 mm)
HEAD_SCREW_PILOT=2.2; HEAD_SCREW_CLEAR=2.9; HEAD_BOSS=5.6   # M2.5 x 8 screws, back plate into the head
TILT=12.0                 # head leans back this many degrees
HEAD_SETBACK=10.0         # head's front face, behind the base's front edge
HEAD_GAP=2.0              # gap between the head and the top of the base

# Stem and base
STEM_W=16.0; STEM_T=6.0; GROOVE=(6.0,1.8)   # stem width and thickness; wire groove on its back (width, depth)
TENON=9.0                 # how far the stem reaches down into the base
BASE_W=88.0; BASE_D=72.0; BASE_H=24.0; BASE_R=5.0
FLOOR=2.0; ROOF=2.4
POST_D=5.6; SCREW_PILOT=2.2; SCREW_CLEAR=2.9; SCREW_HEAD=5.4   # M2.5 x 10 screws, floor into the base
FOOT=8.6; FOOT_DEPTH=0.8  # 3M Bumpon SJ5302 pockets
USB_CUT=(13.0,8.0)        # opening for the ESP32's USB plug (width, height)
TEXT_H=6.2; TEXT_DEPTH=0.8; TEXT_MARGIN=10.0   # LAYERHOUND on the base, and room left at each end

# Derived
HEAD_D=FRONT+FLANGE+RING_T+WIRE_GAP+PADDLE_T          # head depth
BORE=HEAD_OD-2*WALL
R=HEAD_OD/2; T=math.radians(TILT)
RING_BACK=PADDLE_T+WIRE_GAP                           # where the ring's back sits (head frame z)
BOSS_R=BORE/2-HEAD_BOSS/2+0.6                         # boss columns, merged into the wall
# Head frame -> world: back-centre at (0, yB, zB), face tilted back by TILT
ZB=BASE_H+HEAD_GAP+R*math.cos(T)
YB=HEAD_SETBACK+HEAD_D*math.cos(T)
STEM_TOP=-(BORE/2-FIT)+4.0                            # stem starts a little inside the back plate
STEM_LEN=(ZB-BASE_H+TENON)/math.cos(T)                # from the head's centre down to TENON below the base top

def head_to_world():
 c,s=math.cos(T),math.sin(T)
 return [[1,0,0,0],[0,s,-c,YB],[0,c,s,ZB],[0,0,0,1]]

def to_world(m):
 M=head_to_world()
 return m.transform([[M[0][0],M[0][1],M[0][2],M[0][3]],[M[1][0],M[1][1],M[1][2],M[1][3]],[M[2][0],M[2][1],M[2][2],M[2][3]]])

# ---- Head ----------------------------------------------------------------------------------
def head():
 # Cup open at the back; the bezel (front) at z = HEAD_D
 h=cyl(0,0,0,HEAD_D,HEAD_OD)-cyl(0,0,-1,HEAD_D-FRONT+1,BORE)
 h=h-cyl(0,0,HEAD_D-FRONT-1,FRONT+2,WINDOW)
 # Two screw bosses at 3 and 9 o'clock, from the back plate to the bezel, merged into the wall
 for x in (-BOSS_R,BOSS_R):
  h=h+(cyl(x,0,PADDLE_T,HEAD_D-PADDLE_T,HEAD_BOSS)-cyl(x,0,PADDLE_T-1,HEAD_D-PADDLE_T-FRONT+1,HEAD_SCREW_PILOT))
 # Notch at the bottom of the rim where the stem comes out
 return h-box(-STEM_W/2-FIT,-R-1,-1,STEM_W/2+FIT,-BORE/2+1,STEM_T+FIT)

def emblem_shapes():
 colors,(w,hh)=emblem_mod.emblem(EMBLEM_W,root=str(ROOT),head_only=True)
 return {n:translate(s,-w/2,-hh/2) for n,s in colors.items() if not s.is_empty}

def diffuser(shapes):
 # Translucent disc: a plug flush with the bezel, and a flange behind it
 plug=cyl(0,0,HEAD_D-FRONT,FRONT,WINDOW-2*FIT)
 flange=cyl(0,0,HEAD_D-FRONT-FLANGE,FLANGE,WINDOW+2*FLANGE_EXTRA)
 d=plug+flange
 cut=union(section(s).extrude(INLAY+1).translate([0,0,HEAD_D-INLAY]) for s in shapes.values())
 return d-cut

def emblem_inlays(shapes):
 return {n:section(s).extrude(INLAY+0.01).translate([0,0,HEAD_D-INLAY]) for n,s in shapes.items()}

# ---- Paddle: back plate, ring holders, stem --------------------------------------------------
def paddle():
 plate=cyl(0,0,0,PADDLE_T,BORE-2*FIT)
 # Screw holes into the head's bosses
 for x in (-BOSS_R,BOSS_R): plate=plate-cyl(x,0,-1,PADDLE_T+2,HEAD_SCREW_CLEAR)
 # Three ribs press the ring's back (on its inner edge, clear of the solder pads on its outer part),
 # with a finger that reaches into the ring's hole to centre it
 ribs=[]
 for ang in (90,210,330):
  rib=box(RING_ID/2+0.3,-0.7,PADDLE_T,RING_ID/2+2.2,0.7,RING_BACK)
  finger=box(RING_ID/2-0.9,-0.7,PADDLE_T,RING_ID/2-0.15,0.7,RING_BACK+1.6)
  ribs.append((rib+finger).rotate([0,0,ang]))
 # Stem: from inside the plate down into the base
 stem=box(-STEM_W/2,-STEM_LEN,0,STEM_W/2,STEM_TOP,STEM_T)
 p=plate+union(ribs)+stem
 # Wire path: a hole through the plate at the bottom, then a groove down the stem's back
 hole_y=-(RING_OD/2)-3
 p=p-box(-GROOVE[0]/2,hole_y-3,-1,GROOVE[0]/2,hole_y+3,STEM_T+1)
 p=p-box(-GROOVE[0]/2,-STEM_LEN-1,-1,GROOVE[0]/2,hole_y,GROOVE[1])
 return p

def stem_slot():
 # The stem's outline, with clearance, as it passes through the base (for the slot and its sleeve)
 return to_world(box(-STEM_W/2-FIT,-STEM_LEN-20,-FIT,STEM_W/2+FIT,STEM_TOP,STEM_T+FIT))

# ---- Base ----------------------------------------------------------------------------------
X0,X1=-BASE_W/2,BASE_W/2
ESP_X=X0+WALL+0.6+ESP_W/2           # ESP32 along the left wall, USB against the back wall
ESP_BACK=BASE_D-WALL-0.3             # USB end of the ESP32, just off the back wall
ESP_Y0=ESP_BACK-ESP_L                # front end of the ESP32
# Screw posts: three corners, and one beside the ESP32 (which fills the back-left corner)
POSTS=[(X0+WALL+3.2,WALL+3.2),(X1-WALL-3.2,WALL+3.2),(X1-WALL-3.2,BASE_D-WALL-3.2),(ESP_X+ESP_W/2+0.6+POST_D/2,BASE_D-WALL-3.2)]
SHIFTER_X=(X1-WALL-1.5-SHIFTER_BOARD[0],X1-WALL-1.5)   # shifter board along the right side
USB_Z=FLOOR+ESP_PINS+ESP_PCB+1.8     # middle of the USB plug

def base(slot):
 # Tight inside corners (1 mm), so the ESP32 can sit in the back-left corner
 b=rbox(X0,0,FLOOR,X1,BASE_D,BASE_H,BASE_R)-rbox(X0+WALL,WALL,FLOOR-1,X1-WALL,BASE_D-WALL,BASE_H-ROOF,1.0)
 # Posts from the roof down to the floor; screws come up through the floor
 for x,y in POSTS: b=b+(cyl(x,y,FLOOR,BASE_H-FLOOR,POST_D)-cyl(x,y,FLOOR-1,BASE_H-FLOOR-2,SCREW_PILOT))
 # The stem's slot, and a sleeve around it under the roof so the stem is held firmly
 collar=(to_world(box(-STEM_W/2-FIT-2,-STEM_LEN-20,-FIT-2,STEM_W/2+FIT+2,STEM_TOP,STEM_T+FIT+2)))^box(X0,0,BASE_H-TENON+1,X1,BASE_D,BASE_H)
 b=b+collar-slot
 # USB opening at the back
 b=b-box(ESP_X-USB_CUT[0]/2,BASE_D-WALL-1,USB_Z-USB_CUT[1]/2,ESP_X+USB_CUT[0]/2,BASE_D+1,USB_Z+USB_CUT[1]/2)
 # LAYERHOUND on the front, cut in
 words=text_shape('LAYERHOUND',TEXT_H)
 a,c,d,e=words.bounds; words=translate(words,-(a+d)/2,-(c+e)/2)
 b=b-section(words).extrude(TEXT_DEPTH+1).rotate([90,0,0]).translate([0,TEXT_DEPTH,FLOOR+(BASE_H-FLOOR)/2])
 return b

def base_bottom():
 f=rbox(X0,0,0,X1,BASE_D,FLOOR,BASE_R)
 for x,y in POSTS: f=f-cyl(x,y,-1,FLOOR+2,SCREW_CLEAR)-cyl(x,y,-1,1+1.2,SCREW_HEAD)
 # Keep the ESP32 against the back wall and the left wall: a stop at its front end, and a guide
 # along its right edge near the front (the post beside it guides the back)
 xr=ESP_X+ESP_W/2+FIT
 f=f+box(ESP_X-ESP_W/2+3,ESP_Y0-FIT-1.6,FLOOR,ESP_X+ESP_W/2-3,ESP_Y0-FIT,FLOOR+4)
 f=f+box(xr,ESP_Y0,FLOOR,xr+1.6,ESP_Y0+20,FLOOR+4)
 for x,y in ((X0+11,11),(X1-11,11),(X0+11,BASE_D-11),(X1-11,BASE_D-11)):
  f=f-cyl(x,y,-1,1+FOOT_DEPTH,FOOT)
 return f

# ---- Checks --------------------------------------------------------------------------------
def checks(slot):
 problems=[]
 if WINDOW<RING_OD+2: problems.append('the window is narrower than the LED ring')
 if WINDOW+2*FLANGE_EXTRA>BORE-2*HEAD_BOSS: problems.append('the diffuser flange runs into the screw bosses')
 if BOSS_R-HEAD_BOSS/2<RING_OD/2+1: problems.append('the screw bosses run into the LED ring')
 if EMBLEM_W>RING_ID-2: problems.append('the hound is wider than the ring\'s centre')
 a,_,d,_=text_shape('LAYERHOUND',TEXT_H).bounds
 if d-a>BASE_W-2*TEXT_MARGIN: problems.append(f'LAYERHOUND ({d-a:.0f} mm) is too wide for the base; lower TEXT_H')
 if RING_BACK+RING_T>HEAD_D-FRONT-FLANGE+0.01: problems.append('the LED ring doesn\'t fit behind the diffuser')
 if STEM_T+FIT>RING_BACK: problems.append('the stem reaches the LED ring inside the head')
 inside_w=BASE_W-2*WALL; inside_d=BASE_D-2*WALL; inside_h=BASE_H-FLOOR-ROOF
 if ESP_L>inside_d-POST_D-2: problems.append('the ESP32 is longer than the base')
 if SHIFTER_BOARD[1]>inside_d-2*POST_D-2: problems.append('the shifter board is longer than the base')
 if max(ESP_PINS+ESP_PCB+3.5,SHIFTER_H)>inside_h: problems.append('the electronics are taller than the inside of the base')
 # Where the stem (with its collar) comes down inside the base: it must miss both boards
 tenon=to_world(box(-STEM_W/2-FIT-2,-STEM_LEN-20,-FIT-2,STEM_W/2+FIT+2,STEM_TOP,STEM_T+FIT+2))^box(X0,0,BASE_H-TENON,X1,BASE_D,BASE_H)
 x0,y0,_,x1,y1,_=tenon.bounding_box()
 if x0<ESP_X+ESP_W/2+1: problems.append('the stem comes down onto the ESP32')
 if x1>SHIFTER_X[0]-1: problems.append('the stem comes down onto the shifter board')
 if y0<WALL+1 or y1>BASE_D-WALL-1: problems.append('the stem comes down through the base\'s front or back wall')
 if problems: sys.exit('Doesn\'t fit: '+'; '.join(problems))
 print(f'head: {HEAD_OD:g} mm across, {HEAD_D:.1f} mm deep, tilted {TILT:g}°; ring held {WIRE_GAP:g} mm in front of the back plate')
 print(f'base: {BASE_W:g} x {BASE_D:g} x {BASE_H:g} mm; room inside {inside_w:.0f} x {inside_d:.0f} x {inside_h:.1f} mm')
 print(f'stem enters the base at x {x0:.1f}..{x1:.1f}, y {y0:.1f}..{y1:.1f}; ESP32 ends at x {ESP_X+ESP_W/2:.1f}, shifter board starts at x {SHIFTER_X[0]:.1f}')
 print(f'overall height: {ZB+R*math.cos(T)+HEAD_D*math.sin(T):.0f} mm')

def check_assembly(shapes,slot):
 # Put everything together (with stand-ins for the LED ring and the two boards): nothing may overlap
 parts={'head':to_world(head()),'diffuser':to_world(diffuser(shapes)),'paddle':to_world(paddle()),
  'base':base(slot),'base-bottom':base_bottom(),
  'LED ring':to_world(cyl(0,0,RING_BACK,RING_T,RING_OD)-cyl(0,0,RING_BACK-1,RING_T+2,RING_ID)),
  'ESP32':box(ESP_X-ESP_W/2,ESP_Y0,FLOOR,ESP_X+ESP_W/2,ESP_BACK,FLOOR+ESP_PINS+ESP_PCB+3.5),
  'shifter board':box(SHIFTER_X[0],BASE_D/2-SHIFTER_BOARD[1]/2,FLOOR,SHIFTER_X[1],BASE_D/2+SHIFTER_BOARD[1]/2,FLOOR+SHIFTER_H)}
 names=list(parts); clashes=[]
 for i,a in enumerate(names):
  for b in names[i+1:]:
   v=(parts[a]^parts[b]).volume()
   if v>0.5: clashes.append(f'{a} and {b} ({v:.1f} mm3)')   # parts that only touch measure a hair above 0
 if clashes: sys.exit('Parts overlap when assembled: '+'; '.join(clashes))
 print('assembled: no parts overlap (LED ring, ESP32 and shifter board included)')

# ---- Output --------------------------------------------------------------------------------
def flip(m,depth):
 # Head parts print face-down: turn over so the bezel side is on the bed
 return m.rotate([180,0,0]).translate([0,0,depth])

def main():
 slot=stem_slot(); checks(slot)
 shapes=emblem_shapes(); check_assembly(shapes,slot)
 parts={
  'head':(flip(head(),HEAD_D),'head-flip'),
  'diffuser':(flip(diffuser(shapes),HEAD_D),'head-flip'),
  'paddle':(paddle(),'head'),
  'base':(base(slot).rotate([180,0,0]).translate([0,0,BASE_H]),'base-flip'),
  'base-bottom':(base_bottom(),'world'),
 }
 for n,m in emblem_inlays(shapes).items(): parts[f'diffuser-emblem-{n}']=(flip(m,HEAD_D),'head-flip')
 out=HERE/'stl'; out.mkdir(exist_ok=True)
 # Print -> assembled position, for viewer.html
 M=head_to_world(); FLIPZ=[[1,0,0,0],[0,-1,0,0],[0,0,-1,HEAD_D],[0,0,0,1]]
 BFLIP=[[1,0,0,0],[0,-1,0,0],[0,0,-1,BASE_H],[0,0,0,1]]; I=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
 mul=lambda a,b:[[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
 place={'head-flip':mul(M,FLIPZ),'head':M,'base-flip':BFLIP,'world':I}
 assembly=[]
 for name,(m,frame) in parts.items():
  t=save(m,out/f'ring-{name}.stl')
  print(f'ring-{name}.stl','watertight' if t.is_watertight else 'NOT WATERTIGHT',t.bounds.round(1).tolist())
  assembly.append({'file':f'stl/ring-{name}.stl','matrix':place[frame]})
 (out/'assembly.json').write_text(json.dumps(assembly,indent=1))
 return parts

if __name__=='__main__': main()
