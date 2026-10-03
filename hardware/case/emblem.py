# A simple, printable version of the LayerHound mascot for the case lid.
#
# The ring, gantry rails, print head and filament are drawn as clean shapes; the hound's head and
# collar are traced from the mascot artwork (public/brand/layerhound-mascot.png). The result is
# three flat color regions (blue, gray, white) in mm. Gaps between them, like the ear line, show
# the case's own color, the way the black outlines do in the artwork.
import numpy as np
from PIL import Image
from shapely.affinity import scale as shp_scale, translate
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from skimage import measure, morphology

MASCOT='public/brand/layerhound-mascot.png'
# Positions in the artwork's pixels (590 x 624), measured from the image
RING_C=(297,395); RING_R=(255,283); EYE=(364,250)

def _load(path):
 im=np.array(Image.open(path).convert('RGBA')).astype(float)
 r,g,b,a=(im[...,i] for i in range(4))
 mx=np.maximum(np.maximum(r,g),b); mn=np.minimum(np.minimum(r,g),b); sat=(mx-mn)/np.maximum(mx,1)
 op=a>128; blue=op&(sat>0.45)&(b>r+40)
 return op,blue,mx,sat

def _component(mask,point):
 lab=measure.label(mask,connectivity=1); v=lab[point[1],point[0]]
 return lab==v if v else np.zeros_like(mask)

def _largest(mask,n=1):
 lab=measure.label(mask,connectivity=1)
 if lab.max()==0: return mask
 sizes=np.bincount(lab.ravel()); sizes[0]=0
 keep=np.argsort(sizes)[::-1][:n]
 return np.isin(lab,keep[sizes[keep]>0])

def _smooth(mask,r):
 m=morphology.closing(mask,morphology.disk(r)); return morphology.opening(m,morphology.disk(r))

def _polys(mask,simplify=0.8):
 # Pixel mask -> shapely shape in pixel coordinates (y down), holes handled by nesting
 polys=[]
 for c in measure.find_contours(np.pad(mask,1).astype(float),0.5):
  if len(c)>=4:
   p=Polygon([(x-1,y-1) for y,x in c]).buffer(0)
   if p.area>4: polys.append(p)
 polys.sort(key=lambda p:-p.area); out=[]
 for p in polys:
  for i,q in enumerate(out):
   if q.contains(p.representative_point()): out[i]=q.difference(p); break
  else: out.append(p)
 return unary_union(out).simplify(simplify)

def _rounded(x0,y0,x1,y1,r):
 return box(x0+r,y0+r,x1-r,y1-r).buffer(r,join_style=1)

def emblem_px(root='.'):
 op,blue,mx,sat=_load(f'{root}/{MASCOT}')
 h,w=op.shape; yy,xx=np.mgrid[:h,:w]
 dist=np.hypot(xx-RING_C[0],yy-RING_C[1])
 inside=dist<RING_R[0]-6

 # Collar: the blue band across the neck
 collar=_largest(_smooth(blue&inside&(yy>400),3))
 # Head and neck down to the collar: everything not blue inside the ring, above the filament
 dog=_smooth(op&~blue&inside&(yy>150),4)
 dog=_component(dog&~morphology.dilation(collar,morphology.disk(3)),(300,300))
 dog=morphology.remove_small_holes(dog,max_size=400)
 # White muzzle: the biggest light area on the front of the face
 white=_largest(_smooth(dog&(sat<0.25)&(mx>170)&(xx>320),9))
 # Blue eye: a clean disc with a pupil (the artwork's iris is too thin to print)
 eye_shape=Point(EYE).buffer(19,64).difference(Point(EYE).buffer(7,32))
 eye=np.hypot(xx-EYE[0],yy-EYE[1])<19
 # Ear line and other strong outlines become grooves in the case color
 lines=morphology.opening(dog&(mx<55),morphology.disk(2))
 lines=morphology.remove_small_objects(lines,max_size=400)
 lines=morphology.dilation(lines,morphology.disk(2))

 gray=_polys(dog&~white&~lines&~morphology.dilation(eye,morphology.disk(3)))
 white=_polys(white&~lines)
 head_blue=_polys(collar)|eye_shape

 # Clean shapes: ring, rails, print head, filament (pixel coordinates, y down)
 ring=Point(*RING_C).buffer(RING_R[1],128).difference(Point(*RING_C).buffer(RING_R[0],128))
 # The ring passes behind the head; leave a small gap around the head and collar
 head=unary_union([_polys(dog),head_blue]).buffer(6)
 rails=unary_union([_rounded(108,48,495,66,8),_rounded(108,76,495,94,8)])
 block=_rounded(238,12,357,102,10)
 slots=unary_union([_rounded(266,40,329,49,4),_rounded(266,57,329,66,4),_rounded(266,74,329,83,4)])
 caps=unary_union([Polygon([(205,30),(238,14),(238,102),(205,92)]),Polygon([(390,30),(357,14),(357,102),(390,92)])])
 nozzle=Polygon([(248,106),(352,106),(322,138),(278,138)])
 filament=LineString([(300,136),(300,150),(308,158),(385,160),(397,170),(398,190)]).buffer(9,join_style=1)
 gantry_gray=unary_union([rails.difference(block.buffer(4)).difference(caps.buffer(4)),block.difference(slots)])
 blue_all=unary_union([ring.difference(head).difference(nozzle.buffer(5)),caps,nozzle,filament,head_blue])
 return {'blue':blue_all,'gray':unary_union([gray,gantry_gray]),'white':white},(w,h)

def emblem(width_mm,root='.'):
 # The emblem scaled to width_mm wide, in mm with y up, lower-left corner at (0,0)
 shapes,(w,h)=emblem_px(root)
 x0,y0,x1,y1=unary_union(list(shapes.values())).bounds
 k=width_mm/(x1-x0); out={}
 for name,s in shapes.items():
  s=translate(s,-x0,-y1)
  s=shp_scale(s,xfact=k,yfact=-k,origin=(0,0))
  # Smooth jagged traced edges and drop slivers thinner than a nozzle line (about 0.45 mm),
  # and keep colors apart by a hair so each prints as its own clean region
  out[name]=s.buffer(0.22).buffer(-0.44).buffer(0.14).buffer(0)
 # No overlaps: blue wins over white, white over gray
 out['white']=out['white'].difference(out['blue'].buffer(0.15)).buffer(0)
 out['gray']=out['gray'].difference(out['blue'].union(out['white']).buffer(0.15)).buffer(0)
 return out,((x1-x0)*k,(y1-y0)*k)
