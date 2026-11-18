#include "WatooMAttributeSet.h"
#include "WatooMCombatTags.h"
#include "AbilitySystemBlueprintLibrary.h"
#include "GameplayEffectExtension.h"
#include "Net/UnrealNetwork.h"

UWatooMAttributeSet::UWatooMAttributeSet()
{
	InitHealth(100.f);  InitMaxHealth(100.f);
	InitShield(0.f);    InitMaxShield(100.f);
	InitStamina(100.f); InitMaxStamina(100.f);
	InitMana(100.f);    InitMaxMana(100.f);
	InitAmmo(0.f);      InitMaxAmmo(0.f);
	InitTeamId(0.f);
	InitResistPhysical(0.f); InitResistFire(0.f); InitResistFrost(0.f); InitResistLightning(0.f);
	InitIncomingDamage(0.f); InitIncomingHealing(0.f);
}

void UWatooMAttributeSet::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, Health, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, MaxHealth, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, Shield, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, MaxShield, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, Stamina, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, MaxStamina, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, Mana, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, MaxMana, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, Ammo, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, MaxAmmo, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UWatooMAttributeSet, TeamId, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME(UWatooMAttributeSet, ResistPhysical);
	DOREPLIFETIME(UWatooMAttributeSet, ResistFire);
	DOREPLIFETIME(UWatooMAttributeSet, ResistFrost);
	DOREPLIFETIME(UWatooMAttributeSet, ResistLightning);
}

void UWatooMAttributeSet::ClampToMax(const FGameplayAttribute& Attribute, float& Value) const
{
	float Max = -1.f;
	if (Attribute == GetHealthAttribute()) { Max = GetMaxHealth(); }
	else if (Attribute == GetShieldAttribute()) { Max = GetMaxShield(); }
	else if (Attribute == GetStaminaAttribute()) { Max = GetMaxStamina(); }
	else if (Attribute == GetManaAttribute()) { Max = GetMaxMana(); }
	else if (Attribute == GetAmmoAttribute()) { Max = GetMaxAmmo(); }
	else if (Attribute == GetResistPhysicalAttribute() || Attribute == GetResistFireAttribute()
		|| Attribute == GetResistFrostAttribute() || Attribute == GetResistLightningAttribute()) { Max = 1.f; }
	else { return; }
	Value = FMath::Max(Value, 0.f);
	if (Max >= 0.f) { Value = FMath::Min(Value, Max); }
}

void UWatooMAttributeSet::PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue)
{
	Super::PreAttributeChange(Attribute, NewValue);
	ClampToMax(Attribute, NewValue);
}

void UWatooMAttributeSet::PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const
{
	// Base-value changes from instant effects (costs, pickups, SetNumericAttributeBase) stay inside 0..Max as well.
	Super::PreAttributeBaseChange(Attribute, NewValue);
	ClampToMax(Attribute, NewValue);
}

void UWatooMAttributeSet::PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data)
{
	Super::PostGameplayEffectExecute(Data);
	UAbilitySystemComponent* ASC = &Data.Target;
	const FGameplayAttribute& Attr = Data.EvaluatedData.Attribute;

	if (Attr == GetIncomingDamageAttribute())
	{
		float Damage = FMath::Max(GetIncomingDamage(), 0.f);
		SetIncomingDamage(0.f);
		if (Damage <= 0.f || GetHealth() <= 0.f) { return; }
		const float Absorbed = FMath::Min(Damage, GetShield());
		SetShield(GetShield() - Absorbed);
		Damage -= Absorbed;
		SetHealth(FMath::Clamp(GetHealth() - Damage, 0.f, GetMaxHealth()));

		AActor* Owner = ASC ? ASC->GetAvatarActor() : nullptr;
		FGameplayEventData Hit;
		Hit.EventTag = WatooMTags::Event_Hit;
		Hit.Instigator = Data.EffectSpec.GetContext().GetOriginalInstigator();
		Hit.Target = Owner;
		Hit.EventMagnitude = Absorbed + Damage;
		if (Owner) { UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(Owner, WatooMTags::Event_Hit, Hit); }

		if (GetHealth() <= 0.f && ASC && !ASC->HasMatchingGameplayTag(WatooMTags::State_Dead))
		{
			// UE 5.8: AddReplicatedLooseGameplayTag is gone; the replication state argument replicates the tag to clients.
			ASC->AddLooseGameplayTag(WatooMTags::State_Dead, 1, EGameplayTagReplicationState::TagOnly);
			FGameplayEventData Death = Hit;
			Death.EventTag = WatooMTags::Event_Death;
			if (Owner) { UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(Owner, WatooMTags::Event_Death, Death); }
		}
	}
	else if (Attr == GetIncomingHealingAttribute())
	{
		const float Heal = FMath::Max(GetIncomingHealing(), 0.f);
		SetIncomingHealing(0.f);
		if (GetHealth() > 0.f) { SetHealth(FMath::Clamp(GetHealth() + Heal, 0.f, GetMaxHealth())); }
	}
	else if (Attr == GetHealthAttribute())
	{
		// A direct Health write (respawn / revive effect) brings the character back: allow a new death event.
		float V = GetHealth();
		ClampToMax(Attr, V);
		SetHealth(V);
		if (V > 0.f && ASC && ASC->HasMatchingGameplayTag(WatooMTags::State_Dead))
		{
			ASC->RemoveLooseGameplayTag(WatooMTags::State_Dead, 1, EGameplayTagReplicationState::TagOnly);
		}
	}
}

void UWatooMAttributeSet::OnRep_Health(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, Health, Old); }
void UWatooMAttributeSet::OnRep_MaxHealth(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, MaxHealth, Old); }
void UWatooMAttributeSet::OnRep_Shield(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, Shield, Old); }
void UWatooMAttributeSet::OnRep_MaxShield(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, MaxShield, Old); }
void UWatooMAttributeSet::OnRep_Stamina(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, Stamina, Old); }
void UWatooMAttributeSet::OnRep_MaxStamina(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, MaxStamina, Old); }
void UWatooMAttributeSet::OnRep_Mana(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, Mana, Old); }
void UWatooMAttributeSet::OnRep_MaxMana(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, MaxMana, Old); }
void UWatooMAttributeSet::OnRep_Ammo(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, Ammo, Old); }
void UWatooMAttributeSet::OnRep_MaxAmmo(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, MaxAmmo, Old); }
void UWatooMAttributeSet::OnRep_TeamId(const FGameplayAttributeData& Old) { GAMEPLAYATTRIBUTE_REPNOTIFY(UWatooMAttributeSet, TeamId, Old); }
