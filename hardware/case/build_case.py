# LayerHound case for the Radxa ROCK 4D, with a 40 mm fan blowing across the board.
#
#   python hardware/case/build_case.py        (from the project folder; see README.md here)
#
# Writes print-ready STL files to hardware/case/stl/. Open viewer.html (see README.md) to look at them in 3D.
# Every size is a setting at the top of this file, so the case can be adjusted and rebuilt.
#
# Board facts (Radxa ROCK 4D 2D drawing v1.11): 85 x 56 mm, Raspberry Pi 3 layout, four 2.7 mm
# mounting holes 58 x 49 mm apart. Coordinates below: origin at the board's front-left corner,
# x along the 85 mm edge toward the USB/Ethernet end, y toward the 40-pin header, z up from the floor.
from pathlib import Path
import sys
import numpy as np
from manifold3d import CrossSection, FillRule, JoinType, Manifold, set_circular_segments
from PIL import Image, ImageDraw, ImageFont
from shapely.affinity import scale as shp_scale, skew, translate
from shapely.ops import unary_union

HERE=Path(__file__).resolve().parent; ROOT=HERE.parent.parent
sys.path.insert(0,str(HERE))
import emblem as emblem_mod

set_circular_segments(96)

# ---- Settings (mm) ------------------------------------------------------------------------
WALL=2.4; ROOF=2.4; FLOOR=2.0
STANDOFF=4.0                      # board bottom above the floor
PCB=1.6
HOLES=[(3.5,3.5),(61.5,3.5),(3.5,52.5),(61.5,52.5)]
FAN=40.0; FAN_DEPTH=10.0; FAN_HOLES=32.0; FAN_CENTER_X=42.5   # over the processor and memory
INNER=dict(x0=-1.0,x1=85.6,y0=-0.6,y1=56+1.5+FAN_DEPTH+0.5,z1=45.0)
FIT=0.3                           # gap between the base plate and the shell walls
CORNER=3.0                        # outside corner radius
SCREW_CLEAR=2.9; SCREW_HEAD=5.4; SCREW_PILOT=2.2; POST_D=5.2   # M2.5 screws
FAN_SCREW=3.3
SMA_HOLE=True; SMA=(50.0,34.0); SMA_D=6.6                       # Wi-Fi antenna (left side, y, z)
LOGO_DEPTH=0.6                    # 3 layers at 0.2 mm
PCB_TOP=STANDOFF+PCB

# Port openings: open at the bottom edge of the shell so it lowers straight over the board.
# (wall, center along the wall, width, top height above the floor)
PORTS=[
 ('right',47.5,16.0,PCB_TOP+17.0,'USB 3.0 pair'),
 ('right',29.2,16.0,PCB_TOP+17.0,'USB 2.0 pair'),
 ('right',10.1,17.0,PCB_TOP+14.5,'Ethernet'),
 ('front',11.3,12.0,PCB_TOP+6.5,'USB-C power'),
 ('front',32.0,20.0,PCB_TOP+10.0,'HDMI'),
 ('front',53.6,9.0,PCB_TOP+7.5,'Audio'),
 ('left',29.2,15.0,PCB_TOP+2.5,'microSD'),
 # Small parts at the left edge on the drawing (likely buttons or LEDs)
 ('left',15.6,7.0,PCB_TOP+3.0,'left-edge part'),
 ('left',43.2,8.0,PCB_TOP+3.0,'left-edge parts'),
]

# ---- Helpers ------------------------------------------------------------------------------
def box(x0,y0,z0,x1,y1,z1): return Manifold.cube([x1-x0,y1-y0,z1-z0]).translate([x0,y0,z0])
def rbox(x0,y0,z0,x1,y1,z1,r):
 cs=CrossSection.square([x1-x0-2*r,y1-y0-2*r]).offset(r,JoinType.Round).translate([x0+r,y0+r])
 return cs.extrude(z1-z0).translate([0,0,z0])
def cyl(x,y,z0,h,d): return Manifold.cylinder(h,d/2,d/2).translate([x,y,z0])
def ycyl(x,y0,z,length,d): return Manifold.cylinder(length,d/2,d/2).rotate([-90,0,0]).translate([x,y0,z])
def xcyl(x0,y,z,length,d): return Manifold.cylinder(length,d/2,d/2).rotate([0,90,0]).translate([x0,y,z])
def union(parts):
 out=Manifold()
 for p in parts: out=out+p
 return out

def section(shape):
 # shapely (Multi)Polygon -> manifold CrossSection
 polys=getattr(shape,'geoms',[shape]); contours=[]
 for p in polys:
  if p.is_empty: continue
  contours.append(np.array(p.exterior.coords[:-1]))
  contours+= [np.array(i.coords[:-1]) for i in p.interiors]
 return CrossSection(contours,FillRule.EvenOdd)

OUT=dict(x0=INNER['x0']-WALL,x1=INNER['x1']+WALL,y0=INNER['y0']-WALL,y1=INNER['y1']+WALL)
TOP=INNER['z1']+ROOF
FAN_Z=FAN/2+3.0               # fan center height; the fan sits just above the base plate
FAN_Y=INNER['y1']             # fan presses against the inside of the back wall

# ---- Base: floor plate with standoffs ------------------------------------------------------
def base():
 plate=rbox(INNER['x0']+FIT,INNER['y0']+FIT,-FLOOR,INNER['x1']-FIT,INNER['y1']-FIT,0,1.0)
 b=plate+union(cyl(x,y,0,STANDOFF,6.0) for x,y in HOLES)
 for x,y in HOLES:
  b=b-cyl(x,y,-FLOOR-1,FLOOR+STANDOFF+2,SCREW_CLEAR)-cyl(x,y,-FLOOR-1,1+1.6,SCREW_HEAD)
 # Shallow pockets for stick-on rubber feet (8 mm)
 for x in (INNER['x0']+8,INNER['x1']-8):
  for y in (INNER['y0']+8,INNER['y1']-8): b=b-cyl(x,y,-FLOOR-1,1.5,8.6)
 return b

# ---- Shell: walls, roof, posts, fan mount, vents ------------------------------------------
def port_cut(wall,center,width,top):
 z0=-FLOOR-1
 if wall=='right': return box(INNER['x1']-1,center-width/2,z0,OUT['x1']+1,center+width/2,top)
 if wall=='left': return box(OUT['x0']-1,center-width/2,z0,INNER['x0']+1,center+width/2,top)
 return box(center-width/2,OUT['y0']-1,z0,center+width/2,INNER['y0']+1,top)

def fan_grill():
 # Round intake opening with rings and spokes, in the back wall
 cx,cz=FAN_CENTER_X,FAN_Z
 hole=ycyl(cx,INNER['y1']-1,cz,WALL+2,FAN-2)
 keep=Manifold()
 for r in (6.5,12.0,17.0):
  keep=keep+(ycyl(cx,INNER['y1']-1,cz,WALL+2,2*r+1.6)-ycyl(cx,INNER['y1']-2,cz,WALL+4,2*r-1.6))
 for ang in (0,60,120):
  keep=keep+box(-0.8,0,-FAN/2,0.8,WALL+2,FAN/2).rotate([0,ang,0]).translate([cx,INNER['y1']-1,cz])
 keep=keep+ycyl(cx,INNER['y1']-1,cz,WALL+2,8.0)
 return hole-keep

def vents():
 cuts=[]
 # Front wall: tall slots above the HDMI and USB-C openings
 x=3.0
 while x<=82:
  cuts.append(box(x,OUT['y0']-1,PCB_TOP+16,x+2.0,INNER['y0']+1,INNER['z1']-4)); x+=4.5
 # Right wall: slots above the USB ports
 y=4.0
 while y<=52:
  cuts.append(box(INNER['x1']-1,y,PCB_TOP+21,OUT['x1']+1,y+2.0,INNER['z1']-4)); y+=4.5
 return union(cuts)

def shell(logo_cut):
 body=rbox(OUT['x0'],OUT['y0'],-FLOOR+0.2,OUT['x1'],OUT['y1'],TOP,CORNER)
 body=body-box(INNER['x0'],INNER['y0'],-FLOOR-1,INNER['x1'],INNER['y1'],INNER['z1'])
 # Posts from the roof down to the board's top face; screws come up through the base and board
 for x,y in HOLES:
  body=body+cyl(x,y,PCB_TOP,INNER['z1']-PCB_TOP+0.5,POST_D)
  body=body-cyl(x,y,PCB_TOP-1,10,SCREW_PILOT)
 for wall,center,width,top,_ in PORTS: body=body-port_cut(wall,center,width,top)
 body=body-fan_grill()
 for dx in (-FAN_HOLES/2,FAN_HOLES/2):
  for dz in (-FAN_HOLES/2,FAN_HOLES/2):
   body=body-ycyl(FAN_CENTER_X+dx,INNER['y1']-1,FAN_Z+dz,WALL+2,FAN_SCREW)
 body=body-vents()
 if SMA_HOLE: body=body-xcyl(OUT['x0']-1,SMA[0],SMA[1],WALL+2,SMA_D)
 return body-logo_cut

# ---- Logo on the roof ---------------------------------------------------------------------
def text_shape(text,height_mm,font='/System/Library/Fonts/Supplemental/Arial Black.ttf'):
 # Cap-height-sized outline of the text, slanted like the LayerHound wordmark
 px=40; f=ImageFont.truetype(font,int(height_mm*px*1.4))
 l,t,r,b=f.getbbox(text); im=Image.new('L',(r-l+20,b-t+20),0)
 ImageDraw.Draw(im).text((10-l,10-t),text,font=f,fill=255)
 m=np.array(im)>127
 s=emblem_mod._polys(m,0.5)
 x0,y0,x1,y1=s.bounds
 s=translate(s,-x0,-y1); s=shp_scale(s,xfact=1/px,yfact=-1/px,origin=(0,0))
 s=shp_scale(s,xfact=height_mm/(s.bounds[3]-s.bounds[1]),yfact=height_mm/(s.bounds[3]-s.bounds[1]),origin=(0,0))
 return skew(s,xs=-12,origin=(0,0)).buffer(0)

def fit(shape,x0,y0,x1,y1):
 # Scale shape to fit the box (keeping proportions) and center it there
 a,b,c,d=shape.bounds; k=min((x1-x0)/(c-a),(y1-y0)/(d-b))
 s=shp_scale(translate(shape,-a,-b),xfact=k,yfact=k,origin=(0,0))
 w,h=(c-a)*k,(d-b)*k
 return translate(s,x0+(x1-x0-w)/2,y0+(y1-y0-h)/2)

def logo():
 # Emblem on the left, LAYER / HOUND stacked on the right, read from the front of the case
 colors,_=emblem_mod.emblem(40,root=str(ROOT))
 margin=6.0; mid=OUT['x0']+(OUT['x1']-OUT['x0'])*0.47
 ey0,ey1=OUT['y0']+margin,OUT['y1']-margin
 em_all=unary_union(list(colors.values()))
 a,b,c,d=em_all.bounds; k=min((mid-OUT['x0']-margin*1.5)/(c-a),(ey1-ey0)/(d-b))
 place=lambda s:translate(shp_scale(translate(s,-a,-b),xfact=k,yfact=k,origin=(0,0)),
  OUT['x0']+margin+((mid-OUT['x0']-margin*1.5)-(c-a)*k)/2,ey0+((ey1-ey0)-(d-b)*k)/2)
 parts={n:place(s) for n,s in colors.items()}
 layer=text_shape('LAYER',10); hound=text_shape('HOUND',10)
 gap=4.0; hl=hound.bounds[3]
 words=unary_union([translate(layer,0,hl+gap),hound])
 wx0,wx1=mid+margin*0.5,OUT['x1']-margin; cy=(OUT['y0']+OUT['y1'])/2
 a2,b2,c2,d2=words.bounds; k2=min((wx1-wx0)/(c2-a2),26/(d2-b2))
 tr=lambda s:translate(shp_scale(translate(s,-a2,-b2),xfact=k2,yfact=k2,origin=(0,0)),wx0+((wx1-wx0)-(c2-a2)*k2)/2,cy-(d2-b2)*k2/2)
 parts['white']=parts['white'].union(tr(translate(layer,0,hl+gap)))
 parts['blue']=parts['blue'].union(tr(hound))
 z0=TOP-LOGO_DEPTH
 solids={n:section(s).extrude(LOGO_DEPTH+0.01).translate([0,0,z0]) for n,s in parts.items() if not s.is_empty}
 cut=union(section(s).extrude(LOGO_DEPTH+1).translate([0,0,z0]) for s in parts.values() if not s.is_empty)
 return solids,cut

# ---- Output -------------------------------------------------------------------------------
def save(m,path):
 import trimesh
 mesh=m.to_mesh(); t=trimesh.Trimesh(vertices=mesh.vert_properties[:,:3],faces=mesh.tri_verts,process=True)
 t.export(path); return t

def roof_down(m):
 # Print the shell upside down: roof on the bed, so the logo is crisp and nothing needs supports
 return m.rotate([180,0,0]).translate([0,0,TOP])

def main():
 out=HERE/'stl'; out.mkdir(exist_ok=True)
 solids,cut=logo()
 sh=shell(cut); bs=base()
 meshes={'case-shell.stl':roof_down(sh),'case-base.stl':bs.translate([0,0,FLOOR])}
 for n,s in solids.items(): meshes[f'case-logo-{n}.stl']=roof_down(s)
 info={}
 for name,m in meshes.items():
  t=save(m,out/name); info[name]=(t.is_watertight,t.bounds.round(1).tolist())
 for k,v in info.items(): print(k,'watertight' if v[0] else 'NOT WATERTIGHT',v[1])
 print('outside size: %.1f x %.1f x %.1f mm'%(OUT['x1']-OUT['x0'],OUT['y1']-OUT['y0'],TOP+FLOOR))
 return sh,bs,solids

if __name__=='__main__': main()
