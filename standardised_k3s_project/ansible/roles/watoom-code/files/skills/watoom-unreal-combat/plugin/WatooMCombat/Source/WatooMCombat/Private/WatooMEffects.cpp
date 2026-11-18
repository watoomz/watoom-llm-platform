#include "WatooMEffects.h"
#include "WatooMAttributeSet.h"
#include "WatooMCombatTags.h"
#include "WatooMDamageExecution.h"

namespace
{
	FGameplayModifierInfo SetByCallerModifier(const FGameplayAttribute& Attribute, const FGameplayTag& DataTag)
	{
		FSetByCallerFloat SBC;
		SBC.DataTag = DataTag;
		FGameplayModifierInfo Mod;
		Mod.Attribute = Attribute;
		Mod.ModifierOp = EGameplayModOp::Additive;
		Mod.ModifierMagnitude = FGameplayEffectModifierMagnitude(SBC);
		return Mod;
	}
}

UWatooMGE_Damage::UWatooMGE_Damage()
{
	DurationPolicy = EGameplayEffectDurationType::Instant;
	FGameplayEffectExecutionDefinition Exec;
	Exec.CalculationClass = UWatooMDamageExecution::StaticClass();
	Executions.Add(Exec);
	FGameplayEffectCue Cue;
	Cue.GameplayCueTags.AddTag(WatooMTags::GameplayCue_Hit);
	GameplayCues.Add(Cue);
}

UWatooMGE_Heal::UWatooMGE_Heal()
{
	DurationPolicy = EGameplayEffectDurationType::Instant;
	Modifiers.Add(SetByCallerModifier(UWatooMAttributeSet::GetIncomingHealingAttribute(), WatooMTags::SetByCaller_Healing));
}

UWatooMGE_Cost::UWatooMGE_Cost()
{
	DurationPolicy = EGameplayEffectDurationType::Instant;
	Modifiers.Add(SetByCallerModifier(UWatooMAttributeSet::GetStaminaAttribute(), WatooMTags::SetByCaller_Stamina));
	Modifiers.Add(SetByCallerModifier(UWatooMAttributeSet::GetManaAttribute(), WatooMTags::SetByCaller_Mana));
	Modifiers.Add(SetByCallerModifier(UWatooMAttributeSet::GetAmmoAttribute(), WatooMTags::SetByCaller_Ammo));
}

UWatooMGE_Cooldown::UWatooMGE_Cooldown()
{
	DurationPolicy = EGameplayEffectDurationType::HasDuration;
	FSetByCallerFloat SBC;
	SBC.DataTag = WatooMTags::SetByCaller_Duration;
	DurationMagnitude = FGameplayEffectModifierMagnitude(SBC);
}
