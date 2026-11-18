#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GameplayTagContainer.h"
#include "Engine/EngineTypes.h"
#include "Internationalization/Text.h"
#include "UObject/NameTypes.h"
#include "WatooMCombatData.generated.h"

class UAnimMontage;
class UNiagaraSystem;
class USoundBase;
class UStaticMesh;
class USkeletalMesh;
class UGameplayEffect;
class UCameraShakeBase;

UENUM(BlueprintType)
/** Bow (T-0074): fires like a Semi gun (ammo = arrows, MagazineSize 1 = one nocked arrow, reload = nock) but each shot is an
 *  AWatooMProjectile arrow with gravity instead of a hitscan. */
enum class EWatooMWeaponKind : uint8 { Melee, Gun, Bow };

UENUM(BlueprintType)
enum class EWatooMFireMode : uint8 { Semi, Auto, Burst };

UENUM(BlueprintType)
enum class EWatooMSpellDelivery : uint8 { Projectile, Hitscan, Area, Self };

/** Visual + audio for one combat event; every field optional. */
USTRUCT(BlueprintType)
struct FWatooMFx
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") TObjectPtr<UNiagaraSystem> Niagara = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") TObjectPtr<USoundBase> Sound = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") float Scale = 1.f;
};

/**
 * One melee weapon or gun. Made by the pipeline from a spec JSON (unreal_combat_weapon.py); nothing here needs a Blueprint graph.
 * Timing fallbacks (HitWindow*, FireDelay) are used when the montage carries no WatooM notifies.
 */
UCLASS(BlueprintType)
class WATOOMCOMBAT_API UWatooMWeaponData : public UPrimaryDataAsset
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weapon") EWatooMWeaponKind Kind = EWatooMWeaponKind::Melee;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weapon") FText DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mesh") TObjectPtr<UStaticMesh> StaticMesh = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mesh") TObjectPtr<USkeletalMesh> SkeletalMesh = nullptr;
	/** Character socket or bone the weapon attaches to (hand_r on most humanoids). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mesh") FName AttachSocket = TEXT("hand_r");
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mesh") FTransform AttachOffset;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Damage") float Damage = 20.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Damage", meta = (Categories = "Damage.Type")) FGameplayTag DamageType;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cost") float StaminaCost = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cost") float Cooldown = 0.f;

	/** Locomotion stance while this weapon is equipped (e.g. Sword, Rifle, Staff): the generated anim BP has a state + blend space
	 *  per stance and UWatooMCombatAnimInstance switches to it. None = the anim instance's DefaultStance. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Animation") FName Stance;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Animation") TObjectPtr<UAnimMontage> AttackMontage = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Animation") TObjectPtr<UAnimMontage> ReloadMontage = nullptr;

	// Melee
	/** Sockets on the weapon mesh for the blade sweep; when missing, the sweep runs along the mesh's long axis. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Melee") FName TraceStartSocket = TEXT("TraceStart");
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Melee") FName TraceEndSocket = TEXT("TraceEnd");
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Melee") float TraceRadius = 20.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Melee") float HitWindowStart = 0.25f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Melee") float HitWindowEnd = 0.55f;

	// Gun
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") EWatooMFireMode FireMode = EWatooMFireMode::Semi;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") float RoundsPerMinute = 300.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") int32 BurstCount = 3;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") float Range = 10000.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") float FalloffStart = 3000.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") float FalloffEnd = 8000.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") float FalloffMinMultiplier = 0.5f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") float HeadshotMultiplier = 2.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") FName HeadBone = TEXT("head");
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") float SpreadDegrees = 1.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") int32 PelletsPerShot = 1;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") int32 MagazineSize = 30;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") int32 StartingReserveAmmo = 90;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") float ReloadSeconds = 2.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") FName MuzzleSocket = TEXT("Muzzle");
	/** Channel of the hitscan trace. Pawn: characters block it (the default Pawn capsule IGNORES Visibility, so a Visibility
	 *  trace passes through every character - T-0063, 2026-11-18) and world geometry with BlockAll/BlockAllDynamic blocks it too. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Gun") TEnumAsByte<ECollisionChannel> TraceChannel = ECC_Pawn;

	// Bow (projectile weapon): Range sets the arrow's lifespan, Damage/DamageType/HeadshotMultiplier apply on impact
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Bow") float ProjectileSpeed = 5000.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Bow") float ProjectileGravityScale = 0.6f;
	/** The arrow's mesh (its +X is the flight direction); none = only the trail (TracerFx) shows. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Bow") TObjectPtr<UStaticMesh> ProjectileMesh = nullptr;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") FWatooMFx AttackFx;   // swing whoosh / muzzle flash
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") TObjectPtr<UNiagaraSystem> TracerFx = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") FWatooMFx ImpactFx;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") TSubclassOf<UCameraShakeBase> FireCameraShake;

	/** Guns and bows carry a magazine and reserve (ammo attribute, reload ability); melee does not. */
	bool UsesAmmo() const { return Kind == EWatooMWeaponKind::Gun || Kind == EWatooMWeaponKind::Bow; }
	float SecondsPerShot() const { return RoundsPerMinute > 0.f ? 60.f / RoundsPerMinute : 0.2f; }
	/** 1 inside FalloffStart, FalloffMinMultiplier beyond FalloffEnd, linear in between. */
	float FalloffMultiplier(float Distance) const;
};

/** One spell. Made from a spell spec (unreal_combat_spell.py); VFX from unreal_niagara_fx.py recipes. */
UCLASS(BlueprintType)
class WATOOMCOMBAT_API UWatooMSpellData : public UPrimaryDataAsset
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Spell") FText DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Spell") EWatooMSpellDelivery Delivery = EWatooMSpellDelivery::Projectile;
	/** Unique cooldown tag for this spell, e.g. Cooldown.Spell.Fireball (registered by the pipeline). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Spell") FGameplayTag CooldownTag;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cost") float ManaCost = 20.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cost") float Cooldown = 2.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Effect") float Damage = 30.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Effect", meta = (Categories = "Damage.Type")) FGameplayTag DamageType;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Effect") float Healing = 0.f;
	/** Projectile explosion / area radius (cm); 0 = single target. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Effect") float Radius = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Effect") float Range = 3000.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Effect") float ProjectileSpeed = 2500.f;
	/** Optional extra effect on every target hit (burn, slow, stun...). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Effect") TSubclassOf<UGameplayEffect> StatusEffect;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Animation") TObjectPtr<UAnimMontage> CastMontage = nullptr;
	/** Seconds into the cast when the spell is released (fallback when the montage has no Event.Fire notify). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Animation") float ReleaseDelay = 0.35f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Animation") FName CastSocket = TEXT("hand_r");
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") FWatooMFx CastFx;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") TObjectPtr<UNiagaraSystem> ProjectileFx = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") FWatooMFx ImpactFx;
};

UENUM(BlueprintType)
enum class EWatooMItemKind : uint8 { Weapon, Spell, Ammo, Consumable };

/** A pickup: grants a weapon or spell, adds reserve ammo, or restores health/shield/mana. */
UCLASS(BlueprintType)
class WATOOMCOMBAT_API UWatooMItemData : public UPrimaryDataAsset
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") EWatooMItemKind Kind = EWatooMItemKind::Consumable;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") FText DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") TObjectPtr<UStaticMesh> PickupMesh = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") TObjectPtr<UWatooMWeaponData> Weapon = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") TObjectPtr<UWatooMSpellData> Spell = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") int32 Ammo = 0;
	/** Ammo items: the gun the rounds are for; empty = the equipped gun (else the first gun carried). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") TObjectPtr<UWatooMWeaponData> AmmoFor = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") float RestoreHealth = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") float RestoreShield = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item") float RestoreMana = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FX") FWatooMFx PickupFx;
};
