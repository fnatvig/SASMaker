import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

fname1 = sys.argv[1]
fname2 = sys.argv[2]

src_ied = sys.argv[3]
src1, src2 = None, None
if src_ied == 'LIED10':
    src1 = '00:09:8e:21:73:33'
    src2 = 'a2:2e:d6:80:a8:0b'
elif src_ied == 'LIED11':
    src1 = '00:09:8e:21:73:32'
    src2 = 'a2:2e:d6:80:a8:21'
elif src_ied == 'LIED12':
    src1 = '00:09:8e:21:73:31'
    src2 = 'a2:2e:d6:80:a8:2c'
elif src_ied == 'TIED13':
    src1 = '00:09:8e:21:73:27'
    src2 = 'a2:2e:d6:80:a8:8f'
elif src_ied == 'BIED100':
    src1 = '00:09:8e:21:73:25'
    src2 = 'a2:2e:d6:80:a8:bb'

attr = sys.argv[4]

print("Files to analyze: " + fname1 + " and " + fname2)
print("Source (MAC) to analyze in " + fname1 + ": " + src1)
print("Source (MAC) to analyze in " + fname2 + ": " + src2)
print("Attribute to analyze: " + attr)

df1 = pd.read_excel(fname1)
df2 = pd.read_excel(fname2)

values1 = df1[df1["Source"] == src1][attr]
t1 = df1[df1["Source"] == src1]["EpochArrivalTime"] - df1["EpochArrivalTime"][0]

values2 = df2[df2["Source"] == src2][attr]
t2 = df2[df2["Source"] == src2]["EpochArrivalTime"] - df2["EpochArrivalTime"][0]

t_end = 25

mask1 = [t <= t_end for t in t1]
mask2 = [t <= t_end for t in t2]
y_min = min(min(np.array(values1)[mask1]), min(np.array(values2)[mask2]))
y_end = max(max(np.array(values1)[mask1]), max(np.array(values2)[mask2]))
y_end_with_margin = y_end*1.1  
diff = y_end_with_margin-y_end
y_min -= diff
fig, ax = plt.subplots()
ax.plot(t1, [int(float(i)) for i in values1], 'b-*', label='Reference')
ax.plot(t2, [int(float(i)) for i in values2], 'r-*', label='SASMaker')
plt.ylabel(attr)
plt.xlabel("time")
plt.xlim((0, t_end))
plt.ylim((y_min, y_end_with_margin))
ax.yaxis.set_major_locator(MaxNLocator(integer=True))
ax.legend()
plt.title(f'{attr} for {src_ied} over time')
plt.show()
