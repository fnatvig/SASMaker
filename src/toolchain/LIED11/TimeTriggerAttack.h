#ifndef TIMETRIGGERATTACK_H
#define TIMETRIGGERATTACK_H
#include <stdio.h>
#include <signal.h>
#include <time.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include "xmlParser.h"

//adding these
void insertPacket(struct InsertAttack* iAttack);
void createDoSAttackThread(struct DosAttack* dAttack);
void ModifyArray(char** array,struct ModifyAttack* mAttack);
void ModifyArrayTriggerByTime(struct ModifyAttack* mAttack);

void setTimerforInsertAttack(struct InsertAttack* inAttack );
void setTimerforDosAttack(struct DosAttack* dosAttack );
void setTimerforModifyAttack(struct ModifyAttack* mofAttack);
void launch_modify_attack_thread(union sigval v);
void launch_insert_attack_thread(union sigval v);
void launch_dos_attack_thread(union sigval v);

#endif
