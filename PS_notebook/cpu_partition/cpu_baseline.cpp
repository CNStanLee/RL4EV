// Native-CPU baseline: the same feature kernel and quantised network that run in the PL, compiled with g++ and timed per call.
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <vector>
#include <algorithm>
#include "emi_feat_hls.h"
#include "emi_detector_axi.h"
static std::vector<float> load(const char* f){ std::vector<float> v; std::ifstream in(f); float x; while(in>>x) v.push_back(x); return v; }
int main(int argc,char**argv){
  int N = argc>1 ? atoi(argv[1]) : 2000;
  std::vector<float> buf=load("buf_raw.dat"); if(buf.size()<EF_N*EF_C){printf("buf %zu\n",buf.size());return 1;}
  float feat[EF_NF], logit[EMI_DET_N_OUT], amp[EMI_DET_N_OUT]; unsigned flags=0; double acc=0;
  using clk=std::chrono::steady_clock; std::vector<double> tf(N), td(N);
  for(int i=0;i<N;i++){
    auto t0=clk::now(); emi_feat_hls(buf.data(), i==0, feat); auto t1=clk::now();
    emi_detector_axi(feat, logit, amp, &flags, i==0); auto t2=clk::now();
    tf[i]=std::chrono::duration<double,std::micro>(t1-t0).count(); td[i]=std::chrono::duration<double,std::micro>(t2-t1).count(); acc+=logit[0]+feat[3];
  }
  auto stat=[&](std::vector<double> v,const char*n){ std::sort(v.begin(),v.end()); printf("%-10s n=%d median=%.1f us p99=%.1f us max=%.1f us\n",n,N,v[N/2],v[(int)(0.99*N)],v[N-1]); };
  stat(tf,"feature"); stat(td,"network"); printf("flags=0x%x logit0=%.3f (checksum %.3f)\n",flags,logit[0],acc);
  return 0;
}
