import hashlib,json
import numpy as np
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score,confusion_matrix
LEVELS=['low','medium','high']
def classify(humidity,holes,mold):
    rng=np.random.default_rng(31)
    x=np.column_stack([rng.uniform(30,90,600),rng.integers(0,31,600),rng.uniform(0,25,600)])
    # 专家规则构造的合成训练样本，不能替代真实馆藏外部验证。
    y=np.where((x[:,0]>=72)|(x[:,2]>=10),'high',np.where((x[:,0]>=60)|(x[:,1]>=10)|(x[:,2]>=2),'medium','low'))
    train,test=train_test_split(np.arange(len(x)),test_size=.25,random_state=31,stratify=y)
    model=DecisionTreeClassifier(max_depth=5,min_samples_leaf=4,random_state=31).fit(x[train],y[train])
    prediction=model.predict(x[test])
    return str(model.predict([[humidity,holes,mold]])[0]),{'macro_f1':float(f1_score(y[test],prediction,average='macro')),'confusion_matrix':confusion_matrix(y[test],prediction,labels=LEVELS).tolist(),'labels':LEVELS,'train_count':len(train),'test_count':len(test),'seed':31,'dataset_sha256':hashlib.sha256(x.tobytes()+y.tobytes()).hexdigest(),'data_source':'专家规则合成样本；留出指标仅证明内部可复现性'}
