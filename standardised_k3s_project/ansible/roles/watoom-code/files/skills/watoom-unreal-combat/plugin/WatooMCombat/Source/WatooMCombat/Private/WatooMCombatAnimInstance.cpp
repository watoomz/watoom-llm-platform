#include "WatooMCombatAnimInstance.h"
#include "WatooMCombatCharacter.h"
#include "WatooMCombatData.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "KismetAnimationLibrary.h"
#include "UObject/UnrealType.h"

namespace
{
	const FString StancePrefix = TEXT("bStance_");
}

void UWatooMCombatAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();
	UClass* C = GetClass();
	SpeedProp = C->FindPropertyByName(TEXT("Speed"));
	DirectionProp = C->FindPropertyByName(TEXT("Direction"));
	InAirProp = CastField<FBoolProperty>(C->FindPropertyByName(TEXT("bInAir")));
	DeadProp = CastField<FBoolProperty>(C->FindPropertyByName(TEXT("bIsDead")));
	StanceProps.Reset();
	for (TFieldIterator<FBoolProperty> It(C); It; ++It)
	{
		const FString N = It->GetName();
		if (N.StartsWith(StancePrefix)) { StanceProps.Add(FName(*N.RightChop(StancePrefix.Len())), *It); }
	}
}

void UWatooMCombatAnimInstance::SetNumber(FProperty* Prop, double Value)
{
	if (FDoubleProperty* D = CastField<FDoubleProperty>(Prop)) { D->SetPropertyValue_InContainer(this, Value); }
	else if (FFloatProperty* F = CastField<FFloatProperty>(Prop)) { F->SetPropertyValue_InContainer(this, static_cast<float>(Value)); }
}

void UWatooMCombatAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);
	const APawn* Pawn = TryGetPawnOwner();
	if (!Pawn) { return; }
	const FVector V = Pawn->GetVelocity();
	SetNumber(SpeedProp, V.Size2D());
	SetNumber(DirectionProp, V.SizeSquared2D() > 1.f ? UKismetAnimationLibrary::CalculateDirection(V, Pawn->GetActorRotation()) : 0.f);

	const ACharacter* Char = Cast<ACharacter>(Pawn);
	if (InAirProp) { InAirProp->SetPropertyValue_InContainer(this, Char && Char->GetCharacterMovement() && Char->GetCharacterMovement()->IsFalling()); }

	const AWatooMCombatCharacter* Combat = Cast<AWatooMCombatCharacter>(Pawn);
	if (DeadProp) { DeadProp->SetPropertyValue_InContainer(this, Combat && Combat->IsDead()); }

	const UWatooMWeaponData* W = Combat ? Combat->GetEquippedWeapon() : nullptr;
	FName Stance = (W && !W->Stance.IsNone()) ? W->Stance : DefaultStance;
	if (!StanceProps.Contains(Stance)) { Stance = DefaultStance; } // a weapon whose stance this skeleton has no state for
	ActiveStance = Stance;
	for (const TPair<FName, FBoolProperty*>& P : StanceProps) { P.Value->SetPropertyValue_InContainer(this, P.Key == Stance); }
}
