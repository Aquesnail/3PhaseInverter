# -*- coding: utf-8 -*-
"""0.42" OLED (042-7240TSWPG01-H16) 3D 模型生成器
数据来源: SPEC 042-7240TSWPG01-H16 VER A, page 5 (Mechanical Drawing)

坐标系 = 封装局部坐标（与 FPC_16_0.65 封装对齐）:
  X : 沿 16 pin 焊盘排列方向（pitch 0.65，跨距 9.75）
  Y : 垂直焊盘方向
  Z : 0 = 板面（焊盘所在面），+Z 指向远离 PCB 的一侧

生成:
  OLED042_FPC16_wrap.step/.wrl : 焊在板底、FPC 绕过板边折到板正面（默认）
  OLED042_FPC16_flat.step/.wrl : FPC 展开平铺（长度 23mm，便于核对焊盘位置）
生成预览: OLED042_preview_wrap.png / _flat.png
"""
import os, math, sys
import cadquery as cq

# ---------------- 参数（mm） ----------------
PITCH      = 0.65      # 焊盘间距 (P0.65)
NPIN       = 16
FING_W     = 0.35      # 手指宽 (0.35±0.03)
FING_L     = 1.00      # 接触长度 (~0.75~1.0)
FPC_W      = 11.25     # FPC 在接触区宽 (11.25±0.2)
FPC_T      = 0.10      # FPC 厚度(含铜/覆盖膜，手册基材 0.05 + 走线)
STIFF_T    = 0.10      # 接触区补强板
PANEL_W    = 12.0      # 屏体宽 (12.0±0.15 Panel)
PANEL_L    = 11.0      # 屏体长 (11.0±0.15 Panel)
PANEL_T    = 1.25      # 屏体厚度 (1.25±0.1)
BOARD_T    = 1.60      # 你的板厚
EDGE_Y     = 6.00      # 焊盘中心到板边距离（可按实际改）
PANEL_OFF  = 0.05      # 屏体与 FPC 的胶层
OUTDIR     = r"D:\3phase_inverter\Hardware\G474VC_Core\libs\lcsc\3dmodels"

def box_pts(x0,x1,y0,y1,z0,z1):
    """轴对齐长方体 -> (center, dims)，坐标顺序自动归一化"""
    xa,xb=min(x0,x1),max(x0,x1)
    ya,yb=min(y0,y1),max(y0,y1)
    za,zb=min(z0,z1),max(z0,z1)
    return ((xa+xb)/2,(ya+yb)/2,(za+zb)/2), (xb-xa,yb-ya,zb-za)

class Model:
    def __init__(self):
        self.parts=[]   # (center, dims, color) 轴对齐盒
        self.segs=[]    # (p0, p1, width, thick, normal, color) 任意方向条带
    def box(self,x0,x1,y0,y1,z0,z1,color=(0.32,0.36,0.42)):
        c,d=box_pts(x0,x1,y0,y1,z0,z1); self.parts.append((c,d,color))
    def seg(self,p0,p1,width,thick,normal,color):
        self.segs.append((p0,p1,width,thick,normal,color))

def q_boxes(m):
    subs=[]
    for c,d,col in m.parts:
        subs.append(cq.Workplane("XY").box(d[0],d[1],d[2]).translate(c))
    for p0,p1,w,t,n,col in m.segs:
        v=cq.Vector(p1[0]-p0[0],p1[1]-p0[1],p1[2]-p0[2])
        L=v.Length
        if L<1e-6: continue
        xd=v.normalized()
        nd=cq.Vector(*n).normalized()
        # 让 xd 与 nd 正交
        nd2=(nd - xd*(xd.dot(nd))).normalized()
        o=cq.Vector((p0[0]+p1[0])/2,(p0[1]+p1[1])/2,(p0[2]+p1[2])/2)
        pl=cq.Plane(origin=o, xDir=xd, normal=nd2)
        subs.append(cq.Workplane(pl).box(L,w,t))
    s=subs[0]
    for x in subs[1:]: s=s.union(x)
    return s

def write_wrl(m, path, title):
    out=["#VRML V2.0 utf8","# %s"%title]
    out.append("Transform {\n  scale 1 1 1\n  children [")
    def quad(idx):
        return ", ".join("%d, %d, %d, -1"%(a,b,c) for a,b,c in [
            (0,1,2),(0,2,3),(4,6,5),(4,7,6),(0,4,5),(0,5,1),(1,5,6),(1,6,2),(2,6,7),(2,7,3),(3,7,4),(3,4,0)])
    def emit(verts,col):
        pts=", ".join("%.5f %.5f %.5f"%v for v in verts)
        out.append("    Shape {")
        out.append("      appearance Appearance { material Material { diffuseColor %.3f %.3f %.3f } }"%col)
        out.append("      geometry IndexedFaceSet { coord Coordinate { point [ %s ] } coordIndex [ %s ] solid FALSE creaseAngle 1.0 }"%(pts,quad(0)))
        out.append("    }")
    for c,d,col in m.parts:
        hx,hy,hz=d[0]/2,d[1]/2,d[2]/2
        cx,cy,cz=c
        V=[(cx-hx,cy-hy,cz-hz),(cx+hx,cy-hy,cz-hz),(cx+hx,cy+hy,cz-hz),(cx-hx,cy+hy,cz-hz),
           (cx-hx,cy-hy,cz+hz),(cx+hx,cy-hy,cz+hz),(cx+hx,cy+hy,cz+hz),(cx-hx,cy+hy,cz+hz)]
        emit(V,col)
    for p0,p1,w,t,n,col in m.segs:
        vx=[p1[i]-p0[i] for i in range(3)]; L=math.sqrt(sum(v*v for v in vx))
        if L<1e-9: continue
        ax=[v/L for v in vx]
        nd=[float(x) for x in n]
        d=sum(ax[i]*nd[i] for i in range(3))
        nd=[nd[i]-ax[i]*d for i in range(3)]
        nl=math.sqrt(sum(v*v for v in nd)); nd=[v/nl for v in nd]
        ay=[ax[1]*nd[2]-ax[2]*nd[1], ax[2]*nd[0]-ax[0]*nd[2], ax[0]*nd[1]-ax[1]*nd[0]]
        V=[]
        for si in (0,1):
            for ti in (-0.5,0.5):
                for wi in (-0.5,0.5):
                    p=[p0[i]+ax[i]*L*si + ay[i]*w*wi + nd[i]*t*ti for i in range(3)]
                    V.append(tuple(p))
        # 重排为 box 顶点顺序：(0,0,0)(1,0,0)(1,1,0)(0,1,0)(0,0,1)(1,0,1)(1,1,1)(0,1,1)
        def get(a,b,c): return V[a*4+b*2+c]
        VV=[get(0,0,0),get(1,0,0),get(1,1,0),get(0,1,0),get(0,0,1),get(1,0,1),get(1,1,1),get(0,1,1)]
        emit(VV,col)
    out.append("  ]\n}")
    open(path,"w",encoding="ascii",newline="\n").write("\n".join(out)+"\n")

# ---------------- 模型 ----------------
C_GLASS=(0.10,0.10,0.12)     # 屏玻璃（深色）
C_POL  =(0.05,0.30,0.10)     # 偏振片/视角面（绿，示意可视区）
C_FPC  =(0.85,0.55,0.10)     # FPC（琥珀色）
C_STF  =(0.55,0.35,0.10)     # 补强板
C_PAD  =(0.80,0.80,0.30)     # 金手指

def build(variant="wrap", edge_y=EDGE_Y, board_t=BOARD_T):
    m=Model()
    x_half=FPC_W/2
    # --- 金手指（16 触点，与焊盘对齐）---
    for k in range(NPIN):
        cx=(-(NPIN-1)/2 + k)*PITCH
        m.box(cx-FING_W/2, cx+FING_W/2, -FING_L/2, FING_L/2, 0, 0.02, C_PAD)
    # --- 接触区补强 + FPC 主体 ---
    m.box(-x_half,x_half, -FING_L/2, FING_L/2, 0.02, 0.02+FPC_T+STIFF_T, C_STF)
    if variant=="flat":
        # FPC 平铺：从接触区沿 +Y 延伸，屏体在其末端
        y0=FING_L/2
        y1=y0+11.0
        m.box(-x_half,x_half, y0, y1, 0.02, 0.02+FPC_T, C_FPC)
        # 屏体
        m.box(-PANEL_W/2, PANEL_W/2, y1, y1+PANEL_L, 0.02+FPC_T+PANEL_OFF, 0.02+FPC_T+PANEL_OFF+PANEL_T, C_GLASS)
        # 可视区（示意）
        m.box(-PANEL_W/2+1.0, PANEL_W/2-1.0, y1+1.0, y1+PANEL_L-1.0, 0.02+FPC_T+PANEL_OFF+PANEL_T, 0.02+FPC_T+PANEL_OFF+PANEL_T+0.05, C_POL)
    else:
        # FPC 从接触区沿 +Y 到板边，绕过板边(90°+90°)，转到板另一面，向 -Y 铺开
        z_bot = 0.02+FPC_T        # 板底 FPC 上表面
        z_top = -board_t-0.02     # 板顶 FPC 下表面... 用板顶面 z=-board_t
        m.box(-x_half,x_half, FING_L/2, edge_y, 0.02, 0.02+FPC_T, C_FPC)            # 板底走线
        m.box(-x_half,x_half, edge_y, edge_y+FPC_T, 0.02, -board_t-0.02, C_FPC)     # 绕板边（竖直段）
        y_end = edge_y - PANEL_L - 1.0
        m.box(-x_half,x_half, y_end, edge_y, -board_t-0.02-FPC_T, -board_t-0.02, C_FPC)  # 板顶走线
        # 屏体贴在 FPC 外侧（板顶上方）
        z0=-board_t-0.02-FPC_T-PANEL_OFF-PANEL_T
        m.box(-PANEL_W/2, PANEL_W/2, y_end-0.5, y_end-0.5+PANEL_L, z0, z0+PANEL_T, C_GLASS)
        # 可视区示意
        m.box(-PANEL_W/2+0.95, PANEL_W/2-0.95, y_end-0.5+1.0, y_end-0.5+PANEL_L-1.0, z0-0.05, z0, C_POL)
    return m

def preview(m, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig=plt.figure(figsize=(11,7),dpi=130)
    ax=fig.add_subplot(111,projection='3d')
    polys=[];cols=[]
    def add_box(c,d,col,alpha=1.0):
        hx,hy,hz=d[0]/2,d[1]/2,d[2]/2; cx,cy,cz=c
        V=[(cx-hx,cy-hy,cz-hz),(cx+hx,cy-hy,cz-hz),(cx+hx,cy+hy,cz-hz),(cx-hx,cy+hy,cz-hz),
           (cx-hx,cy-hy,cz+hz),(cx+hx,cy-hy,cz+hz),(cx+hx,cy+hy,cz+hz),(cx-hx,cy+hy,cz+hz)]
        F=[(0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        for f in F: polys.append([V[i] for i in f]); cols.append(col)
    for c,d,col in m.parts: add_box(c,d,col)
    for p0,p1,w,t,n,col in m.segs:  # 简化：按中点小盒画
        mid=[(p0[i]+p1[i])/2 for i in range(3)]
        L=math.dist(p0,p1)
        add_box(mid,(max(L,0.2),w,t),col)
    pc=Poly3DCollection(polys,facecolors=[(c[0],c[1],c[2],0.95) for c in cols],edgecolors=(0,0,0,0.25),linewidths=0.3)
    ax.add_collection3d(pc)
    xs=[p[0] for pl in polys for p in pl]; ys=[p[1] for pl in polys for p in pl]; zs=[p[2] for pl in polys for p in pl]
    ax.set_xlim(min(xs),max(xs)); ax.set_ylim(min(ys),max(ys)); ax.set_zlim(min(zs),max(zs))
    ax.set_box_aspect((max(xs)-min(xs)+1e-6, max(ys)-min(ys)+1e-6, max(zs)-min(zs)+1e-6))
    ax.view_init(elev=22, azim=-58)
    ax.set_xlabel("X (pad row) mm"); ax.set_ylabel("Y mm"); ax.set_zlabel("Z (out of PCB) mm")
    ax.set_title(title, fontsize=10)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)

if __name__=="__main__":
    os.makedirs(OUTDIR,exist_ok=True)
    for variant,title in (("wrap","0.42 OLED folded over board edge"),("flat","0.42 OLED FPC flat (unfolded)")):
        m=build(variant)
        sp=os.path.join(OUTDIR,"OLED042_FPC16_%s.step"%variant)
        wp=os.path.join(OUTDIR,"OLED042_FPC16_%s.wrl"%variant)
        cq.exporters.export(q_boxes(m), sp)
        write_wrl(m, wp, title)
        preview(m, os.path.join(OUTDIR,"OLED042_preview_%s.png"%variant), title)
        print("%-6s -> %s (%d B), %s (%d B)"%(variant, os.path.basename(sp), os.path.getsize(sp),
                                             os.path.basename(wp), os.path.getsize(wp)))
