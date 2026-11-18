#pragma once

#include "CoreMinimal.h"
#include "AttributeSet.h"
#include "AbilitySystemComponent.h"
#include "GameplayEffectExtension.h"
#include "UObject/CoreNet.h"
#include "WatooMAttributeSet.generated.h"

#define WATOOM_ATTRIBUTE_ACCESSORS(ClassName, PropertyName) \
	GAMEPLAYATTRIBUTE_PROPERTY_GETTER(ClassName, PropertyName) \
	GAMEPLAYATTRIBUTE_VALUE_GETTER(PropertyName) \
	GAMEPLAYATTRIBUTE_VALUE_SETTER(PropertyName) \
	GAMEPLAYATTRIBUTE_VALUE_INITTER(PropertyName)

/**
 * One attribute set for every WatooMCombat character.
 * - Health/Shield/Stamina/Mana are clamped to 0..Max (PreAttributeChange for current values, PostGameplayEffectExecute for base).
 * - IncomingDamage / IncomingHealing are META attributes (server only, never replicated): GE_Damage's execution writes
 *   IncomingDamage, and PostGameplayEffectExecute spends it on Shield first, then Health.
 * - Health reaching 0 sends Event.Death to the owner and adds State.Dead (server), once.
 * - Resist* are 0..1 fractions taken off damage of that type by the damage execution.
 * - TeamId: hits between two non-zero equal team ids do nothing (no friendly fire).
 * - Ammo is the equipped gun's magazine (the character keeps reserve ammo per weapon).
 */
UCLASS()
class WATOOMCOMBAT_API UWatooMAttributeSet : public UAttributeSet
{
	GENERATED_BODY()

public:
	UWatooMAttributeSet();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue) override;
	virtual void PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const override;
	virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override;

	UPROPERTY(BlueprintReadOnly, Category = "Vitals", ReplicatedUsing = OnRep_Health) FGameplayAttributeData Health;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, Health)
	UPROPERTY(BlueprintReadOnly, Category = "Vitals", ReplicatedUsing = OnRep_MaxHealth) FGameplayAttributeData MaxHealth;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, MaxHealth)
	UPROPERTY(BlueprintReadOnly, Category = "Vitals", ReplicatedUsing = OnRep_Shield) FGameplayAttributeData Shield;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, Shield)
	UPROPERTY(BlueprintReadOnly, Category = "Vitals", ReplicatedUsing = OnRep_MaxShield) FGameplayAttributeData MaxShield;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, MaxShield)
	UPROPERTY(BlueprintReadOnly, Category = "Resources", ReplicatedUsing = OnRep_Stamina) FGameplayAttributeData Stamina;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, Stamina)
	UPROPERTY(BlueprintReadOnly, Category = "Resources", ReplicatedUsing = OnRep_MaxStamina) FGameplayAttributeData MaxStamina;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, MaxStamina)
	UPROPERTY(BlueprintReadOnly, Category = "Resources", ReplicatedUsing = OnRep_Mana) FGameplayAttributeData Mana;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, Mana)
	UPROPERTY(BlueprintReadOnly, Category = "Resources", ReplicatedUsing = OnRep_MaxMana) FGameplayAttributeData MaxMana;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, MaxMana)
	UPROPERTY(BlueprintReadOnly, Category = "Resources", ReplicatedUsing = OnRep_Ammo) FGameplayAttributeData Ammo;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, Ammo)
	UPROPERTY(BlueprintReadOnly, Category = "Resources", ReplicatedUsing = OnRep_MaxAmmo) FGameplayAttributeData MaxAmmo;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, MaxAmmo)
	UPROPERTY(BlueprintReadOnly, Category = "Team", ReplicatedUsing = OnRep_TeamId) FGameplayAttributeData TeamId;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, TeamId)
	UPROPERTY(BlueprintReadOnly, Category = "Resist", Replicated) FGameplayAttributeData ResistPhysical;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, ResistPhysical)
	UPROPERTY(BlueprintReadOnly, Category = "Resist", Replicated) FGameplayAttributeData ResistFire;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, ResistFire)
	UPROPERTY(BlueprintReadOnly, Category = "Resist", Replicated) FGameplayAttributeData ResistFrost;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, ResistFrost)
	UPROPERTY(BlueprintReadOnly, Category = "Resist", Replicated) FGameplayAttributeData ResistLightning;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, ResistLightning)

	// Meta attributes: server-only scratch values, never replicated.
	UPROPERTY(BlueprintReadOnly, Category = "Meta") FGameplayAttributeData IncomingDamage;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, IncomingDamage)
	UPROPERTY(BlueprintReadOnly, Category = "Meta") FGameplayAttributeData IncomingHealing;
	WATOOM_ATTRIBUTE_ACCESSORS(UWatooMAttributeSet, IncomingHealing)

protected:
	UFUNCTION() void OnRep_Health(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_MaxHealth(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_Shield(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_MaxShield(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_Stamina(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_MaxStamina(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_Mana(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_MaxMana(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_Ammo(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_MaxAmmo(const FGameplayAttributeData& Old);
	UFUNCTION() void OnRep_TeamId(const FGameplayAttributeData& Old);

private:
	/** Clamp a current value to 0..its max (no max = only >= 0). */
	void ClampToMax(const FGameplayAttribute& Attribute, float& Value) const;
};
