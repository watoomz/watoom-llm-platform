#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectExecutionCalculation.h"
#include "WatooMDamageExecution.generated.h"

/**
 * Server-side damage for GE_WatooMDamage.
 *   damage = Data.Damage * Data.DamageMultiplier(default 1) * (1 - Resist<Type>)   ->  IncomingDamage (meta)
 * The damage type is the first Damage.Type.* tag on the effect spec (asset or dynamic tags); none = Physical.
 * Source and target with the same non-zero TeamId deal nothing to each other (friendly fire off).
 * A target that already has State.Dead takes nothing.
 */
UCLASS()
class WATOOMCOMBAT_API UWatooMDamageExecution : public UGameplayEffectExecutionCalculation
{
	GENERATED_BODY()

public:
	UWatooMDamageExecution();
	virtual void Execute_Implementation(const FGameplayEffectCustomExecutionParameters& ExecutionParams,
		FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const override;

	/** Pure rule, exposed for tests and for UI previews: resist is clamped to 0..1, multiplier to >= 0. */
	UFUNCTION(BlueprintPure, Category = "WatooM|Combat")
	static float ComputeDamage(float BaseDamage, float Multiplier, float Resist, float SourceTeam, float TargetTeam);
};
