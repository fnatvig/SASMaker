import sys
import pandas as pd
import matplotlib.pyplot as plt

fname1 = sys.argv[1]
fname2 = sys.argv[2]
src1 = sys.argv[3]
src2 = sys.argv[4]
attr = sys.argv[5]

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


plt.plot(t1, values1, '*')
plt.plot(t2, values2, 'o')
plt.ylabel(attr)
plt.xlabel("time")
plt.show()
