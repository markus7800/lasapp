functions {
    real mydist_lpdf(real x, real p) {
        real lp;
        
        if (x < 0) {
            reject("reject x");
        } else if (p < 0) {
            reject("reject p");
        } else {
            lp = 0;
        }
        return lp;
  }
  real mydist2(real x, real p) {
        real lp;
        
        if (x < 0) {
            reject("reject x 2");
        } else if (p < 0) {
            reject("reject p 2");
        } else {
            lp = 0;
        }
        return lp;
  }
}

data {
    real y;
}

parameters {
    real p;
    real x;
}

model {
    // x ~ mydist(p);

    // this is detected --warn-pedantic
    // real lp;
    // lp  = 0;
    // lp += mydist_lpdf(x | p);
    // lp += mydist2(x, p);
    // lp += mydist2(y, p);
    // target += lp;
    

    // this is not
    target += mydist_lpdf(x | p);
    target += mydist2(x, p);
    target += mydist2(y, p);
}