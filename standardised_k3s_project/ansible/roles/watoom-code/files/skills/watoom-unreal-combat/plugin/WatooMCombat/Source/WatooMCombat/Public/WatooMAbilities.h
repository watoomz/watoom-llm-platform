#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbility.h"
#include "Abilities/GameplayAbilityTypes.h"
#include "Components/MeshComponent.h"
#include "Engine/TimerHandle.h"
#include "GameFramework/Actor.h"
#include "GameplayAbilitySpec.h"
#include "GameplayAbilitySpecHandle.h"
#include "GameplayEffect.h"
#include "GameplayTagContainer.h"
#include "Math/MathFwd.h"
#include "UObject/NameTypes.h"
#include "WatooMAbilities.generated.h"

class AWatooMCombatCharacter;
class UWatooMWeaponData;
class UWatooMSpellData;
class UAnimMontage;

/**
 * Base for every WatooM ability: data-driven cost (stamina/mana/ammo through UWatooMGE_Cost) and cooldown
 * (UWatooMGE_Cooldown + a per-ability Cooldown.* tag), server-only damage helpers. Blocked while dead or stunned.
 */
UCLASS(Abstract)
class WATOOMCOMBAT_API UWatooMGameplayAbility : public UGameplayAbility
{
	GENERATED_BODY()
public:
	UWatooMGameplayAbility();

	virtual bool CheckCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, FGameplayTagContainer* OptionalRelevantTags) const override;
	virtual void ApplyCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const override;
	virtual const FGameplayTagContainer* GetCooldownTags() const override;
	virtual void ApplyCooldown(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const override;

	/** Server: apply GE_WatooMDamage from this ability's owner to Target. Returns false when Target has no ability system. */
	bool ApplyDamage(AActor* Target, float Damage, float Multiplier, const FGameplayTag& DamageType) const;
	bool ApplyHealing(AActor* Target, float Amount) const;
	bool ApplyEffectClass(AActor* Target, TSubclassOf<UGameplayEffect> Effect) const;

protected:
	virtual float GetStaminaCost() const { return 0.f; }
	virtual float GetManaCost() const { return 0.f; }
	virtual float GetAmmoCost() const { return 0.f; }
	virtual float GetCooldownSeconds() const { return 0.f; }
	virtual FGameplayTag GetCooldownTag() const { return FGameplayTag(); }

	AWatooMCombatCharacter* GetCombatCharacter() const;
	/** True on the server (or standalone): the only place damage, ammo and spawns happen. */
	bool IsServer() const;
	/** Play a montage through PlayMontageAndWait; calls EndAbility when it finishes or is interrupted (unless bEndOnFinish is false). */
	void PlayMontage(UAnimMontage* Montage, bool bEndOnFinish = true);
	UFUNCTION() void OnMontageFinished();
	void EndNow();

private:
	mutable FGameplayTagContainer CooldownTagsScratch;
};

/** Melee swing with the equipped melee weapon: montage + blade sweep during the hit window, each target hit once per swing. */
UCLASS()
class WATOOMCOMBAT_API UWatooMGA_Melee : public UWatooMGameplayAbility
{
	GENERATED_BODY()
public:
	UWatooMGA_Melee();
	virtual bool CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const override;
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	/** Blade segment in world space for a weapon mesh: TraceStart/TraceEnd sockets, else the mesh's longest bounds axis. */
	static void BladeSegment(const class UMeshComponent* Mesh, FName StartSocket, FName EndSocket, FVector& OutStart, FVector& OutEnd);

protected:
	virtual float GetStaminaCost() const override;
	virtual float GetCooldownSeconds() const override;
	virtual FGameplayTag GetCooldownTag() const override;

private:
	UFUNCTION() void OnWindowOpen(FGameplayEventData Payload);
	UFUNCTION() void OnWindowClose(FGameplayEventData Payload);
	void OpenWindow();
	void CloseWindow();
	void Sweep();
	/** A window that saw fewer than MinSweeps frames (slow server tick): one sphere sweep along the weapon's reach in front. */
	void ReachSweep();
	int32 SweepCount = 0;
	static constexpr int32 MinSweeps = 3;

	TSet<TWeakObjectPtr<AActor>> HitThisSwing;
	FVector LastStart = FVector::ZeroVector, LastEnd = FVector::ZeroVector;
	bool bWindowOpen = false, bWindowEventSeen = false;
	FTimerHandle SweepTimer, OpenTimer, CloseTimer, EndTimer;
	TWeakObjectPtr<UWatooMWeaponData> Weapon;
};

/** Gun: semi / auto (held) / burst; hitscan with spread, pellets, falloff and headshots; ammo is the Ammo attribute. */
UCLASS()
class WATOOMCOMBAT_API UWatooMGA_Gun : public UWatooMGameplayAbility
{
	GENERATED_BODY()
public:
	UWatooMGA_Gun();
	virtual bool CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const override;
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void InputReleased(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

protected:
	virtual float GetAmmoCost() const override { return 1.f; }
	virtual float GetCooldownSeconds() const override;
	virtual FGameplayTag GetCooldownTag() const override;

private:
	void FireOnce();
	void FireLoop();
	TWeakObjectPtr<UWatooMWeaponData> Weapon;
	int32 ShotsLeft = 0;
	bool bHeld = false;
	FTimerHandle FireTimer;
};

/** Reload the equipped gun from its reserve; blocks firing (State.Reloading) for ReloadSeconds. */
UCLASS()
class WATOOMCOMBAT_API UWatooMGA_Reload : public UWatooMGameplayAbility
{
	GENERATED_BODY()
public:
	UWatooMGA_Reload();
	virtual bool CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const override;
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
private:
	void Finish();
	FTimerHandle ReloadTimer;
};

/** A spell; its UWatooMSpellData is the ability spec's SourceObject (one spec per known spell). */
UCLASS()
class WATOOMCOMBAT_API UWatooMGA_Spell : public UWatooMGameplayAbility
{
	GENERATED_BODY()
public:
	UWatooMGA_Spell();
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	/** Server: impact at Point (radius from the spell data = area); DirectHit always included. Used by AWatooMProjectile too. */
	void HitTargetsAt(const FVector& Point, AActor* DirectHit, UWatooMSpellData* SpellOverride = nullptr);

protected:
	virtual float GetManaCost() const override;
	virtual float GetCooldownSeconds() const override;
	virtual FGameplayTag GetCooldownTag() const override;

private:
	UWatooMSpellData* GetSpell() const;
	UFUNCTION() void OnReleaseEvent(FGameplayEventData Payload);
	void Release();
	bool bReleased = false;
	FTimerHandle ReleaseTimer;
};
