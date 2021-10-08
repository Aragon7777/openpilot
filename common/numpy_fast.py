def int_rnd(x):
  return int(round(x))

def clip(x, lo, hi):
  return max(lo, min(hi, x))

def mean(x):
  return sum(x) / len(x)

def get_interp(xv, xp, fp):
  hi = 0
  while hi < len(xp) and xv > xp[hi]:
    hi += 1
  low = hi - 1
  if hi == len(xp) and xv > xp[low]:
    return fp[-1]
  if hi == 0:
    return fp[0]
  return (xv - xp[low]) * (fp[hi] - fp[low]) / (xp[hi] - xp[low]) + fp[low]

def interp(x, xp, fp):
  return [get_interp(v, xp, fp) for v in x] if hasattr(x, '__iter__') else get_interp(x, xp, fp)


def get_interp2d(xv, yv, yp, xzp):
  hi = 0
  while hi < len(yp) and yv > yp[hi]:
    hi += 1
  low = hi - 1
  if hi == len(yp) and yv > yp[low]:
    return get_interp(xv, *xzp[-1])

  if hi == 0:
    return get_interp(xv, *xzp[0])

  zlow = get_interp(xv, *xzp[low])
  zhi = get_interp(xv, *xzp[hi])

  return zlow + (zhi - zlow) * (yv - yp[low]) / (yp[hi] - yp[low])

def interp2d(xy, yp, xzp):
  return [get_interp2d(xv, yv, yp, xzp) for xv, yv in xy] if hasattr(xy[0], '__iter__') else get_interp2d(*xy, yp, xzp)
