#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "UObject/NameTypes.h"
#include "UObject/UnrealType.h"
#include "WatooMCombatAnimInstance.generated.h"

/**
 * Parent class for every anim BP the combat pipeline generates (unreal_combat.py "anim" section), for any skeleton.
 * Each frame it writes, BY NAME, the Blueprint variables the generated graph reads, if the BP has them:
 *   Speed (ground speed cm/s), Direction (-180..180 relative to the actor's facing), bInAir, bIsDead,
 *   bStance_<Name> for every stance variable: true only for the active stance.
 * The active stance is the equipped weapon's Stance (UWatooMWeaponData::Stance), else DefaultStance ("Unarmed").
 * By name (reflection) so a game's stances are pure data: a new stance needs a BP variable + state, not new C++.
 * Montages (attacks, casts, hit reacts, reloads) play through the graph's slot node, so they are not in here.
 */
UCLASS()
class WATOOMCOMBAT_API UWatooMCombatAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	virtual void NativeInitializeAnimation() override;
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;

	/** Stance used with no weapon (or a weapon without a Stance). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "WatooM|Anim") FName DefaultStance = TEXT("Unarmed");

	UFUNCTION(BlueprintPure, Category = "WatooM|Anim") FName GetActiveStance() const { return ActiveStance; }

private:
	void SetNumber(FProperty* Prop, double Value);
	FProperty* SpeedProp = nullptr;
	FProperty* DirectionProp = nullptr;
	FBoolProperty* InAirProp = nullptr;
	FBoolProperty* DeadProp = nullptr;
	TMap<FName, FBoolProperty*> StanceProps; // stance name -> bStance_<Name>
	FName ActiveStance;
};
