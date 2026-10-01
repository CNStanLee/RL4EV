// fair CPU baseline of the network: the deployed weights (exported by hls4ml as text) evaluated in plain float32, no ap_fixed emulation
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <vector>
#include <cmath>
static std::vector<float> rd(const char* f){ std::vector<float> v; std::ifstream in(f); std::string s; while(std::getline(in,s)){ for(char&c:s) if(c==',') c=' '; std::istringstream is(s); float x; while(is>>x) v.push_back(x);} return v; }
struct Mlp { std::vector<float> w0,b0,w1,b1,w2,b2; float h0[64],h1[64]; void load(){ w0=rd("firmware/weights/w3.txt"); b0=rd("firmware/weights/b3.txt"); w1=rd("firmware/weights/w6.txt"); b1=rd("firmware/weights/b6.txt"); w2=rd("firmware/weights/w9.txt"); b2=rd("firmware/weights/b9.txt"); }
  inline void run(const float* x, float* out){
    for(int j=0;j<64;j++){ float a=b0[j]; const float* w=&w0[j]; for(int i=0;i<48;i++) a+=x[i]*w[i*64]; h0[j]=a>0?a:0; }
    for(int j=0;j<64;j++){ float a=b1[j]; const float* w=&w1[j]; for(int i=0;i<64;i++) a+=h0[i]*w[i*64]; h1[j]=a>0?a:0; }
    for(int j=0;j<10;j++){ float a=b2[j]; const float* w=&w2[j]; for(int i=0;i<64;i++) a+=h1[i]*w[i*10]; out[j]=a; } } };
