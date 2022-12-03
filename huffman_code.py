strok = 'acceptedresult' 
res = sorted({(i,strok.count(i)) for i in strok}, key = lambda x: x[1])
kol = len(res)
final = {}
def min2():
    global res
    if len(res) >= 2:
        res = sorted(res,key = lambda x: x[1])
        final.setdefault((res[0][0]+res[1][0]),[(res[0][0],0),(res[1][0], 1)])
        res.append((res[0][0]+res[1][0], res[0][1]+res[1][1]))
        res = res[2:]
    elif len(res)==1 and len(final) == 0:
        final.setdefault((res[0][0]),[(res[0][0],0)])
    else: 
        res.pop(0)
while res:
    min2()
kodir = {} 
path = []
def resid(start, end):
    if start == end:
        if len(list(filter(lambda x: x ==strok[0],strok))) == len(strok):
            kodir.setdefault(end, '0')
        else:
            kodir.setdefault(end, ''.join(str(x) for x in path))
            path.clear()
    else:
        for i in range(2):
            if end in final[start][i][0]:
                path.append(final[start][i][1])
                return resid(final[start][i][0], end)
hash_strok = ''
for i in strok:
    if i not in kodir:
        resid(max(final, key = lambda x: len(x)), i) 
    hash_strok += kodir[i]            
print(kol, len(hash_strok)) 
for k, v in sorted(kodir.items(), key = lambda x: len(x[1])):
    print(str(k)+":", v)               
print(hash_strok)