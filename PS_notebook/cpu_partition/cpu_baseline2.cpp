#include <chrono>
#include <algorithm>
#include "mlp_float.cpp"
#include "emi_feat_hls.h"
#include "mpcc_r_hls.h"
int main(int argc,char**argv){ int N=argc>1?atoi(argv[1]):2000; std::vector<float> buf=rd("buf_raw.dat"); Mlp m; m.load(); if(m.w0.size()!=48*64||m.w1.size()!=64*64||m.w2.size()!=64*10){printf("weight sizes %zu %zu %zu\n",m.w0.size(),m.w1.size(),m.w2.size());return 1;}
  float feat[48],out[10]; using clk=std::chrono::steady_clock; std::vector<double> tf(N),tn(N),tc(N); double acc=0;
  for(int i=0;i<N;i++){ auto t0=clk::now(); emi_feat_hls(buf.data(), i==0, feat); auto t1=clk::now(); m.run(feat,out); auto t2=clk::now(); tf[i]=std::chrono::duration<double,std::micro>(t1-t0).count(); tn[i]=std::chrono::duration<double,std::micro>(t2-t1).count(); acc+=out[0]; }
  float D=0, dbg[6]; int M=N*100; std::vector<double> tk(M); float th=0;
  for(int i=0;i<M;i++){ th+=2*3.14159f*50*50e-6f; if(th>6.2832f) th-=6.2832f; auto t0=clk::now(); mpcc_r_hls(29.4f*sinf(th), 29.4f*sinf(th), 340.0f*sinf(th), 50e-6f, 600e-6f, 400.0f, th, 0.5f,0.3f,0.2f, 0.1f,0.2f,0.3f, true, 0u, 0.0f, 437u, 0.06f, &D, dbg); auto t1=clk::now(); tk[i]=std::chrono::duration<double,std::micro>(t1-t0).count(); acc+=D; }
  auto st=[&](std::vector<double> v,const char*n){ int n_=v.size(); std::sort(v.begin(),v.end()); printf("%-14s n=%d median=%.2f us p99=%.2f us max=%.1f us\n",n,n_,v[n_/2],v[(int)(0.99*n_)],v[n_-1]); };
  st(tf,"feature(C)"); st(tn,"network(f32)"); st(tk,"mpcc_r tick"); printf("checksum %.3f\n",acc); return 0; }
