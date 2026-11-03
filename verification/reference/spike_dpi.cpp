// Native Windows DPI transport. C-runtime buffers avoid loading a conflicting
// MinGW C++ standard library into XSim. Only STEP/FINISH reach Spike.
#define NOMINMAX
#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DPI_EXPORT extern "C" __declspec(dllexport)
static const char* pin="530af85d83781a3dae31a4ace84a573ec255fefa";
static HANDLE process_handle=NULL, input_pipe=NULL, output_pipe=NULL;
static FILE* audit=NULL;
static unsigned compared=0,total=0;
static bool active=false,cleanup_registered=false;
static char diagnostic[4096]="";

static void close_reference() {
  active=false;
  if(input_pipe) { CloseHandle(input_pipe); input_pipe=NULL; }
  if(process_handle) {
    if(WaitForSingleObject(process_handle,1000)==WAIT_TIMEOUT) {
      TerminateProcess(process_handle,1); WaitForSingleObject(process_handle,1000);
    }
    CloseHandle(process_handle); process_handle=NULL;
  }
  if(output_pipe) { CloseHandle(output_pipe); output_pipe=NULL; }
}
static void cleanup() { close_reference(); if(audit) { fclose(audit); audit=NULL; } }
static int fail(const char* message) {
  snprintf(diagnostic,sizeof(diagnostic),"%s",message);
  if(audit) { fprintf(audit,"ERROR %s\n",diagnostic); fflush(audit); }
  close_reference(); return 1;
}
static bool receive(char* line,size_t capacity) {
  ULONGLONG start=GetTickCount64(); size_t used=0;
  while(GetTickCount64()-start<30000) {
    DWORD available=0,n=0; char c;
    if(!PeekNamedPipe(output_pipe,NULL,0,NULL,&available,NULL)) { fail("reference pipe closed"); return false; }
    if(!available) { Sleep(1); continue; }
    if(!ReadFile(output_pipe,&c,1,&n,NULL) || n!=1) { fail("reference read failed"); return false; }
    if(c=='\n') { line[used]=0; fprintf(audit,"< %s\n",line); fflush(audit); return true; }
    if(c!='\r') {
      if(used+1>=capacity) { fail("oversize reference record"); return false; }
      line[used++]=c;
    }
  }
  fail("reference timeout (30 seconds)"); return false;
}
static bool send(const char* command) {
  DWORD n=0; char line[128]; int size=snprintf(line,sizeof(line),"%s\n",command);
  fprintf(audit,"> %s\n",command); fflush(audit);
  if(size<0 || size>=int(sizeof(line)) || !WriteFile(input_pipe,line,DWORD(size),&n,NULL) || n!=DWORD(size)) {
    fail("reference write failed"); return false;
  }
  return true;
}
static bool append(char* buffer,size_t capacity,size_t* used,char c) {
  if(*used+1>=capacity) return false;
  buffer[(*used)++]=c; buffer[*used]=0; return true;
}
// Windows argv quoting. No cmd.exe or other shell is involved.
static bool append_arg(char* buffer,size_t capacity,size_t* used,const char* arg) {
  if(*used && !append(buffer,capacity,used,' ')) return false;
  // Match Windows list2cmdline: WSL's launcher treats unnecessarily quoted
  // option tokens differently from ordinary CRT programs.
  if(*arg && !strpbrk(arg," \t\"")) {
    for(const char* p=arg;*p;p++) if(!append(buffer,capacity,used,*p)) return false;
    return true;
  }
  if(!append(buffer,capacity,used,'"')) return false;
  size_t slashes=0;
  for(const char* p=arg;*p;p++) {
    if(*p=='\\') { slashes++; continue; }
    size_t copies=(*p=='"')?2*slashes+1:slashes;
    while(copies--) if(!append(buffer,capacity,used,'\\')) return false;
    slashes=0;
    if(!append(buffer,capacity,used,*p)) return false;
  }
  slashes*=2;
  while(slashes--) if(!append(buffer,capacity,used,'\\')) return false;
  return append(buffer,capacity,used,'"');
}
DPI_EXPORT int rv_spike_open(const char* config_path) {
  if(active) return fail("duplicate reference open");
  if(!cleanup_registered) { atexit(cleanup); cleanup_registered=true; }
  if(audit) fclose(audit);
  audit=fopen("spike-live.log","w");
  if(!audit) return fail("cannot open live audit log");
  char args[12][2048],command[32768]="",line[4096],extra;
  FILE* config=fopen(config_path,"r");
  if(!config) return fail("missing live launch configuration");
  unsigned count=0; size_t used=0;
  while(count<12 && fgets(args[count],sizeof(args[count]),config)) {
    size_t n=strlen(args[count]);
    if(!n || args[count][n-1]!='\n') { fclose(config); return fail("truncated live configuration"); }
    while(n && (args[count][n-1]=='\r' || args[count][n-1]=='\n')) args[count][--n]=0;
    if(!append_arg(command,sizeof(command),&used,args[count])) { fclose(config); return fail("launch command too long"); }
    count++;
  }
  bool excess=fgetc(config)!=EOF; fclose(config);
  if(count!=12 || excess || strcmp(args[0],"wsl") || strcmp(args[1],"-d") || strcmp(args[3],"--exec"))
    return fail("invalid live launch configuration");
  unsigned requested=0;
  if(sscanf(args[8],"%u%c",&requested,&extra)!=1 || requested<1 || requested>1000) return fail("invalid reference count");
  SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE}; HANDLE child_in=NULL,child_out=NULL;
  if(!CreatePipe(&child_in,&input_pipe,&sa,0)) return fail("stdin pipe");
  if(!CreatePipe(&output_pipe,&child_out,&sa,0)) { CloseHandle(child_in); return fail("stdout pipe"); }
  if(!SetHandleInformation(input_pipe,HANDLE_FLAG_INHERIT,0) || !SetHandleInformation(output_pipe,HANDLE_FLAG_INHERIT,0)) {
    CloseHandle(child_in); CloseHandle(child_out); return fail("pipe inheritance");
  }
  STARTUPINFOA si={}; si.cb=sizeof(si); si.dwFlags=STARTF_USESTDHANDLES;
  HANDLE child_error=CreateFileA("spike-live-reference.log",GENERIC_WRITE,FILE_SHARE_READ,&sa,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(child_error==INVALID_HANDLE_VALUE) { CloseHandle(child_in); CloseHandle(child_out); return fail("reference stderr log"); }
  si.hStdInput=child_in; si.hStdOutput=child_out; si.hStdError=child_error;
  PROCESS_INFORMATION pi={};
  BOOL ok=CreateProcessA(NULL,command,NULL,NULL,TRUE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi);
  CloseHandle(child_in); CloseHandle(child_out); CloseHandle(child_error);
  if(!ok) return fail("cannot start WSL reference");
  process_handle=pi.hProcess; CloseHandle(pi.hThread);
  if(!receive(line,sizeof(line))) return 1;
  unsigned api=0; char commit[41];
  if(sscanf(line,"READY %u %40s %u %c",&api,commit,&total,&extra)!=3 || api!=1 || strcmp(commit,pin) || total!=requested)
    return fail("reference identity/configuration handshake");
  compared=0; diagnostic[0]=0; active=true; return 0;
}
DPI_EXPORT int rv_spike_check(unsigned pc,unsigned insn,unsigned rd,unsigned data,
    unsigned address,unsigned rmask,unsigned wmask,unsigned rdata,unsigned wdata,
    unsigned trap,unsigned halt,unsigned intr) {
  if(!active) return fail("reference not active");
  char command[64],line[4096],extra;
  snprintf(command,sizeof(command),"STEP %u",compared);
  if(!send(command) || !receive(line,sizeof(line))) return 1;
  unsigned long long n,p,i,r,d,kind,a,v,next,terminal;
  if(sscanf(line,"RET %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu %c",
      &n,&p,&i,&r,&d,&kind,&a,&v,&next,&terminal,&extra)!=10 || n!=compared ||
      p>0xffffffffULL || i>0xffffffffULL || d>0xffffffffULL || r>31 || kind>2 ||
      v>0xffffffffULL || terminal>1 || next>0xffffffffULL || a>0xffffffffULL) return fail("invalid reference retirement");
  const char* field=NULL; unsigned long long expected=0,actual=0;
#define CHECK(label,want,got) if(!field && (want)!=(got)) { field=label; expected=(want); actual=(got); }
  CHECK("pc",p,pc); CHECK("insn",i,insn); CHECK("event",0u,trap|halt|intr);
  CHECK("rd_address",r,rd);
  if(rd) { CHECK("rd_data",d,data); }
  if(kind) {
    CHECK("memory_address",a,address); CHECK("memory_mask",15u,(kind==1?rmask:wmask));
    CHECK("memory_data",v,(kind==1?rdata:wdata));
  }
#undef CHECK
  if(field) {
    snprintf(line,sizeof(line),"mismatch order=%llu field=%s expected=%llu actual=%llu",n,field,expected,actual);
    return fail(line);
  }
  compared++; fprintf(audit,"MATCH %llu\n",n); fflush(audit); return 0;
}
DPI_EXPORT int rv_spike_finish() {
  if(!active || compared!=total) return fail("incomplete reference comparison");
  char line[4096],expected[64];
  if(!send("FINISH") || !receive(line,sizeof(line))) return 1;
  snprintf(expected,sizeof(expected),"PASS %u",compared);
  if(strcmp(line,expected)) return fail("reference completion failed");
  if(WaitForSingleObject(process_handle,5000)!=WAIT_OBJECT_0) return fail("reference exit timeout");
  DWORD exit_code=1;
  if(!GetExitCodeProcess(process_handle,&exit_code) || exit_code) return fail("reference exit failed");
  close_reference(); return 0;
}
DPI_EXPORT const char* rv_spike_error() { return diagnostic; }
DPI_EXPORT void rv_spike_close() { close_reference(); }
