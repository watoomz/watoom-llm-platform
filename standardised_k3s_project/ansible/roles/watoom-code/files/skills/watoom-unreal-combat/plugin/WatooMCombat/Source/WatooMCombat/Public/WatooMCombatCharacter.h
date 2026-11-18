#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AbilitySystemInterface.h"
#include "GameplayTagContainer.h"
#include "Components/InputComponent.h"
#include "Components/MeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/NetSerialization.h"
#include "GameFramework/Controller.h"
#include "Math/MathFwd.h"
#include "UObject/CoreNet.h"
#include "UObject/UObjectGlobals.h"
#include "WatooMCombatCharacter.generated.h"

class UAbilitySystemComponent;
class UWatooMAttributeSet;
class UWatooMWanderComponent;
class UWatooMWeaponData;
class UWatooMSpellData;
class UGameplayAbility;
class USpringArmComponent;
class UCameraComponent;
class UInputMappingContext;
class UInputAction;
class UAnimMontage;
class UNiagaraSystem;
class USoundBase;
struct FInputActionValue;
struct FGameplayEventData;

/** Ability input ids the character binds (GAS addresses input by integer). */
namespace WatooMInput
{
	constexpr int32 Primary = 1;
	constexpr int32 Reload = 2;
	constexpr int32 SpellBase = 10; // spell slot i uses SpellBase + i
}

/**
 * Third-person combat character for any WatooMCombat game. Everything is set as data on a Blueprint child:
 * meshes/anim BP (normal Character fields), StartingWeapons, StartingSpells, TeamId, the input actions, hit/death montages.
 * Owns its AbilitySystemComponent (Mixed replication) and UWatooMAttributeSet; damage only ever runs on the server.
 */
UCLASS()
class WATOOMCOMBAT_API AWatooMCombatCharacter : public ACharacter, public IAbilitySystemInterface
{
	GENERATED_BODY()

public:
	AWatooMCombatCharacter(const FObjectInitializer& ObjectInitializer);

	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override { return AbilitySystem; }
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void BeginPlay() override;
	virtual void PossessedBy(AController* NewController) override;
	virtual void OnRep_PlayerState() override;
	virtual void PawnClientRestart() override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

	// ---------- data (set on the Blueprint child by the pipeline) ----------
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TArray<TObjectPtr<UWatooMWeaponData>> StartingWeapons;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TArray<TObjectPtr<UWatooMSpellData>> StartingSpells;
	/** 0 = no team (everyone can hit it). Same non-zero team = no friendly fire. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "WatooM|Combat") int32 TeamId = 0;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") float StartingMaxHealth = 100.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") float StartingMaxShield = 100.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") float StartingShield = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TObjectPtr<UAnimMontage> HitReactMontage = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TObjectPtr<UAnimMontage> DeathMontage = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") bool bRagdollOnDeath = true;
	/** Ability classes granted at start; defaults are the plugin's melee/gun/reload/spell abilities. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TSubclassOf<UGameplayAbility> MeleeAbility;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TSubclassOf<UGameplayAbility> GunAbility;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TSubclassOf<UGameplayAbility> ReloadAbility;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TSubclassOf<UGameplayAbility> SpellAbility;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Input") TObjectPtr<UInputMappingContext> DefaultMappingContext = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Input") TObjectPtr<UInputAction> MoveAction = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Input") TObjectPtr<UInputAction> LookAction = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Input") TObjectPtr<UInputAction> JumpAction = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Input") TObjectPtr<UInputAction> PrimaryAction = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Input") TObjectPtr<UInputAction> ReloadAction = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Input") TObjectPtr<UInputAction> NextWeaponAction = nullptr;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "WatooM|Input") TArray<TObjectPtr<UInputAction>> SpellActions;

	// ---------- runtime ----------
	UFUNCTION(BlueprintPure, Category = "WatooM|Combat") UWatooMWeaponData* GetEquippedWeapon() const;
	UFUNCTION(BlueprintPure, Category = "WatooM|Combat") UMeshComponent* GetWeaponMeshComponent() const;
	UFUNCTION(BlueprintPure, Category = "WatooM|Combat") bool IsDead() const;
	UFUNCTION(BlueprintPure, Category = "WatooM|Combat") int32 GetReserveAmmo() const;
	UFUNCTION(BlueprintCallable, Category = "WatooM|Combat") void EquipWeapon(int32 Index);
	UFUNCTION(BlueprintCallable, Category = "WatooM|Combat") void EquipNextWeapon();
	/** Server: add a weapon (pickup); returns its slot. Re-picking a held weapon adds its magazine to reserve. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "WatooM|Combat") int32 AddWeapon(UWatooMWeaponData* Weapon);
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "WatooM|Combat") void AddSpell(UWatooMSpellData* Spell);
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "WatooM|Combat") void AddReserveAmmo(int32 Rounds);
	/** Rounds for one gun the character carries (null = equipped gun, else the first gun). Returns rounds added (0 = no such gun). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "WatooM|Combat") int32 AddReserveAmmoFor(UWatooMWeaponData* Gun, int32 Rounds);
	/** Server: move rounds from reserve into the equipped gun's magazine; returns rounds moved. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "WatooM|Combat") int32 ReloadEquipped();
	/** Server: full health/shield/stamina/mana, clears State.Dead (respawn). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "WatooM|Combat") void ResetVitals();
	/** Where shots and spells aim from and to (server-safe: pawn view + control rotation). */
	void GetAim(FVector& OutStart, FVector& OutDirection) const;

	UFUNCTION(NetMulticast, Unreliable) void MulticastPlayFx(UNiagaraSystem* System, USoundBase* Sound, FVector_NetQuantize Location, FRotator Rotation, float Scale);
	UFUNCTION(NetMulticast, Unreliable) void MulticastTracer(UNiagaraSystem* System, FVector_NetQuantize Start, FVector_NetQuantize End);
	UFUNCTION(NetMulticast, Unreliable) void MulticastPlayMontage(UAnimMontage* Montage);
	UFUNCTION(NetMulticast, Reliable) void MulticastDeath();

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TObjectPtr<UAbilitySystemComponent> AbilitySystem;
	/** Off by default; NPCs and creatures roam with "Wander.bEnabled": true in the spec's character defaults. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TObjectPtr<UWatooMWanderComponent> Wander;
	UPROPERTY() TObjectPtr<UWatooMAttributeSet> Attributes;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "WatooM|Camera") TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "WatooM|Camera") TObjectPtr<UCameraComponent> FollowCamera;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TObjectPtr<UStaticMeshComponent> WeaponStatic;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "WatooM|Combat") TObjectPtr<USkeletalMeshComponent> WeaponSkeletal;

	UPROPERTY(ReplicatedUsing = OnRep_Weapons) TArray<TObjectPtr<UWatooMWeaponData>> Weapons;
	UPROPERTY(ReplicatedUsing = OnRep_Weapons) int32 EquippedIndex = INDEX_NONE;
	UPROPERTY(Replicated) TArray<int32> MagazineAmmo;
	UPROPERTY(Replicated) TArray<int32> ReserveAmmo;
	UPROPERTY(Replicated) TArray<TObjectPtr<UWatooMSpellData>> Spells;

	UFUNCTION() void OnRep_Weapons();
	UFUNCTION(Server, Reliable) void ServerEquipWeapon(int32 Index);

private:
	void InitAbilitySystem();
	void GrantStartingAbilities();
	void GrantSpellAbility(UWatooMSpellData* Spell, int32 Slot);
	void ApplyEquippedMesh();
	void StoreMagazine();
	void LoadMagazine();
	void OnHitEvent(const FGameplayEventData* Payload);
	void OnDeathEvent(const FGameplayEventData* Payload);

	void Input_Move(const FInputActionValue& Value);
	void Input_Look(const FInputActionValue& Value);
	void Input_AbilityPressed(int32 InputId);
	void Input_AbilityReleased(int32 InputId);

	bool bAbilitiesGranted = false;
	bool bAbilitySystemReady = false;
};
