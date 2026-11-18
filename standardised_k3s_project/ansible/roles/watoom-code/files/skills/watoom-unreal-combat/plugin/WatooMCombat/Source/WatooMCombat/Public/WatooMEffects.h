#pragma once

#include "CoreMinimal.h"
#include "GameplayEffect.h"
#include "WatooMEffects.generated.h"

/** Instant damage through UWatooMDamageExecution. Caller sets Data.Damage (and optionally Data.DamageMultiplier) and adds one
 *  Damage.Type.* tag as a dynamic asset tag. Fires GameplayCue.Combat.Hit on the target. */
UCLASS()
class WATOOMCOMBAT_API UWatooMGE_Damage : public UGameplayEffect
{
	GENERATED_BODY()
public:
	UWatooMGE_Damage();
};

/** Instant heal: Data.Healing -> IncomingHealing (clamped to MaxHealth; does nothing to the dead). */
UCLASS()
class WATOOMCOMBAT_API UWatooMGE_Heal : public UGameplayEffect
{
	GENERATED_BODY()
public:
	UWatooMGE_Heal();
};

/** Instant ability cost: subtracts Data.Cost.Stamina, Data.Cost.Mana and Data.Cost.Ammo (the ability passes negative values). */
UCLASS()
class WATOOMCOMBAT_API UWatooMGE_Cost : public UGameplayEffect
{
	GENERATED_BODY()
public:
	UWatooMGE_Cost();
};

/** Cooldown: lasts Data.Duration seconds; the ability adds its own Cooldown.<Name> tag as a dynamic granted tag. */
UCLASS()
class WATOOMCOMBAT_API UWatooMGE_Cooldown : public UGameplayEffect
{
	GENERATED_BODY()
public:
	UWatooMGE_Cooldown();
};
