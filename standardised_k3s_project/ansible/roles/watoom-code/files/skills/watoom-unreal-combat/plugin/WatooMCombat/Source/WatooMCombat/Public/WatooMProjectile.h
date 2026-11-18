#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/HitResult.h"
#include "Math/MathFwd.h"
#include "UObject/CoreNet.h"
#include "WatooMProjectile.generated.h"

class USphereComponent;
class UProjectileMovementComponent;
class UNiagaraComponent;
class UWatooMSpellData;
class UWatooMGA_Spell;
class UWatooMWeaponData;
class UWatooMGameplayAbility;
class UStaticMeshComponent;

/**
 * Replicated projectile: a spell (UWatooMGA_Spell) or a bow's arrow (UWatooMGA_Gun with a Bow weapon, T-0074). Spawned only on
 * the server; moves on every machine (replicated movement). On impact the server applies the spell's damage/heal/status
 * (radius = area) or the weapon's damage (x HeadshotMultiplier when the arrow lands within 25 cm of the HeadBone).
 */
UCLASS()
class WATOOMCOMBAT_API AWatooMProjectile : public AActor
{
	GENERATED_BODY()

public:
	AWatooMProjectile();
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Server: speed, range-based lifespan and the trail VFX from the spell; Ability is the caster's spell ability. */
	void InitFromSpell(UWatooMSpellData* InSpell, UWatooMGA_Spell* InAbility);
	/** Server: an arrow - weapon speed and gravity, lifespan from Range, the arrow mesh and TracerFx as its trail. */
	void InitFromWeapon(UWatooMWeaponData* InWeapon, UWatooMGameplayAbility* InAbility);

protected:
	UPROPERTY(VisibleAnywhere, Category = "Projectile") TObjectPtr<USphereComponent> Collision;
	UPROPERTY(VisibleAnywhere, Category = "Projectile") TObjectPtr<UProjectileMovementComponent> Movement;
	UPROPERTY(VisibleAnywhere, Category = "Projectile") TObjectPtr<UNiagaraComponent> Trail;
	UPROPERTY(VisibleAnywhere, Category = "Projectile") TObjectPtr<UStaticMeshComponent> Body;
	UPROPERTY(ReplicatedUsing = OnRep_Spell) TObjectPtr<UWatooMSpellData> Spell;
	UPROPERTY(ReplicatedUsing = OnRep_Weapon) TObjectPtr<UWatooMWeaponData> Weapon;
	UFUNCTION() void OnRep_Weapon();

	UFUNCTION() void OnRep_Spell();
	UFUNCTION() void OnHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit);
	UFUNCTION() void OnOverlap(UPrimitiveComponent* OverlappedComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

private:
	void Impact(const FVector& Point, AActor* Direct);
	TWeakObjectPtr<UWatooMGA_Spell> Ability;
	TWeakObjectPtr<UWatooMGameplayAbility> WeaponAbility;
	bool bDone = false;
};
