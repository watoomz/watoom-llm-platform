#include "WatooMDamageExecution.h"
#include "WatooMAttributeSet.h"
#include "WatooMCombatTags.h"
#include "AbilitySystemComponent.h"

namespace
{
	struct FWatooMDamageStatics
	{
		DECLARE_ATTRIBUTE_CAPTUREDEF(ResistPhysical);
		DECLARE_ATTRIBUTE_CAPTUREDEF(ResistFire);
		DECLARE_ATTRIBUTE_CAPTUREDEF(ResistFrost);
		DECLARE_ATTRIBUTE_CAPTUREDEF(ResistLightning);
		FGameplayEffectAttributeCaptureDefinition TargetTeamDef;
		FGameplayEffectAttributeCaptureDefinition SourceTeamDef;

		FWatooMDamageStatics()
		{
			DEFINE_ATTRIBUTE_CAPTUREDEF(UWatooMAttributeSet, ResistPhysical, Target, false);
			DEFINE_ATTRIBUTE_CAPTUREDEF(UWatooMAttributeSet, ResistFire, Target, false);
			DEFINE_ATTRIBUTE_CAPTUREDEF(UWatooMAttributeSet, ResistFrost, Target, false);
			DEFINE_ATTRIBUTE_CAPTUREDEF(UWatooMAttributeSet, ResistLightning, Target, false);
			TargetTeamDef = FGameplayEffectAttributeCaptureDefinition(UWatooMAttributeSet::GetTeamIdAttribute(), EGameplayEffectAttributeCaptureSource::Target, false);
			SourceTeamDef = FGameplayEffectAttributeCaptureDefinition(UWatooMAttributeSet::GetTeamIdAttribute(), EGameplayEffectAttributeCaptureSource::Source, true);
		}
	};

	const FWatooMDamageStatics& Statics()
	{
		static FWatooMDamageStatics S;
		return S;
	}
}

UWatooMDamageExecution::UWatooMDamageExecution()
{
	RelevantAttributesToCapture.Add(Statics().ResistPhysicalDef);
	RelevantAttributesToCapture.Add(Statics().ResistFireDef);
	RelevantAttributesToCapture.Add(Statics().ResistFrostDef);
	RelevantAttributesToCapture.Add(Statics().ResistLightningDef);
	RelevantAttributesToCapture.Add(Statics().TargetTeamDef);
	RelevantAttributesToCapture.Add(Statics().SourceTeamDef);
}

float UWatooMDamageExecution::ComputeDamage(float BaseDamage, float Multiplier, float Resist, float SourceTeam, float TargetTeam)
{
	if (SourceTeam != 0.f && SourceTeam == TargetTeam) { return 0.f; }
	return FMath::Max(BaseDamage, 0.f) * FMath::Max(Multiplier, 0.f) * (1.f - FMath::Clamp(Resist, 0.f, 1.f));
}

void UWatooMDamageExecution::Execute_Implementation(const FGameplayEffectCustomExecutionParameters& ExecutionParams,
	FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const
{
	const FGameplayEffectSpec& Spec = ExecutionParams.GetOwningSpec();
	const UAbilitySystemComponent* TargetASC = ExecutionParams.GetTargetAbilitySystemComponent();
	if (TargetASC && TargetASC->HasMatchingGameplayTag(WatooMTags::State_Dead)) { return; }

	FAggregatorEvaluateParameters Eval;
	Eval.SourceTags = Spec.CapturedSourceTags.GetAggregatedTags();
	Eval.TargetTags = Spec.CapturedTargetTags.GetAggregatedTags();

	FGameplayTagContainer SpecTags;
	Spec.GetAllAssetTags(SpecTags);
	SpecTags.AppendTags(Spec.GetDynamicAssetTags());

	const FGameplayEffectAttributeCaptureDefinition* ResistDef = &Statics().ResistPhysicalDef;
	if (SpecTags.HasTagExact(WatooMTags::Damage_Type_Fire)) { ResistDef = &Statics().ResistFireDef; }
	else if (SpecTags.HasTagExact(WatooMTags::Damage_Type_Frost)) { ResistDef = &Statics().ResistFrostDef; }
	else if (SpecTags.HasTagExact(WatooMTags::Damage_Type_Lightning)) { ResistDef = &Statics().ResistLightningDef; }

	float Resist = 0.f, SourceTeam = 0.f, TargetTeam = 0.f;
	ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(*ResistDef, Eval, Resist);
	ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(Statics().SourceTeamDef, Eval, SourceTeam);
	ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(Statics().TargetTeamDef, Eval, TargetTeam);

	const float Base = Spec.GetSetByCallerMagnitude(WatooMTags::SetByCaller_Damage, false, 0.f);
	const float Mult = Spec.GetSetByCallerMagnitude(WatooMTags::SetByCaller_DamageMultiplier, false, 1.f);
	const float Damage = ComputeDamage(Base, Mult, Resist, SourceTeam, TargetTeam);
	if (Damage > 0.f)
	{
		OutExecutionOutput.AddOutputModifier(FGameplayModifierEvaluatedData(
			UWatooMAttributeSet::GetIncomingDamageAttribute(), EGameplayModOp::Additive, Damage));
	}
}
